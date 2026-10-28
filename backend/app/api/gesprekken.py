import json
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.responses import StreamingResponse
from pydantic_ai.exceptions import AgentRunError
from pydantic_ai.models import Model
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import EigenGesprek, EigenKennisbank, Session
from app.auth import CurrentUser
from app.config import Settings, get_settings
from app.db import SessionLocal
from app.llm.ollama import OllamaClient, OllamaError
from app.models import Bericht, Gesprek
from app.rag.embedding import embed_query
from app.rag.generation import als_berichten, antwoord_agent, herschrijf, vraag_met_bronnen
from app.rag.retrieval import zoek
from app.schemas import BerichtIn, GesprekDetail, GesprekIn, GesprekOut

log = logging.getLogger(__name__)

kb_router = APIRouter(prefix="/kennisbanken/{kennisbank_id}/gesprekken", tags=["Gesprekken"])
router = APIRouter(prefix="/gesprekken", tags=["Gesprekken"])

NIEUW_GESPREK = "Nieuw gesprek"


@kb_router.get("", response_model=list[GesprekOut])
async def lijst(kb: EigenKennisbank, user: CurrentUser, session: Session):
    return (
        await session.scalars(
            select(Gesprek)
            .where(Gesprek.kennisbank_id == kb.id, Gesprek.owner_sub == user.sub)
            .order_by(Gesprek.created_at.desc())
        )
    ).all()


@kb_router.post("", response_model=GesprekOut, status_code=status.HTTP_201_CREATED)
async def maak(
    body: GesprekIn, kb: EigenKennisbank, user: CurrentUser, session: Session, response: Response
):
    gesprek = Gesprek(kennisbank_id=kb.id, owner_sub=user.sub, titel=body.titel or NIEUW_GESPREK)
    session.add(gesprek)
    await session.commit()
    await session.refresh(gesprek)
    response.headers["Location"] = f"/api/v1/gesprekken/{gesprek.id}"
    return gesprek


@router.get("/{gesprek_id}", response_model=GesprekDetail)
async def lees(gesprek: EigenGesprek, session: Session):
    return await session.scalar(
        select(Gesprek).where(Gesprek.id == gesprek.id).options(selectinload(Gesprek.berichten))
    )


@router.delete("/{gesprek_id}", status_code=status.HTTP_204_NO_CONTENT)
async def verwijder(gesprek: EigenGesprek, session: Session):
    await session.delete(gesprek)
    await session.commit()


def _sse(event: str, data) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post(
    "/{gesprek_id}/berichten",
    response_class=StreamingResponse,
    responses={200: {"content": {"text/event-stream": {}}}},
)
async def stel_vraag(
    body: BerichtIn,
    gesprek: EigenGesprek,
    session: Session,
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
):
    """Stelt een vraag en streamt het antwoord als server-sent events:
    `bronnen` (de gevonden fragmenten), dan `token` per stukje tekst, en tot slot `klaar`
    of `fout`."""
    ollama: OllamaClient = request.app.state.ollama
    chatmodel: Model = request.app.state.chatmodel
    vraag = body.inhoud.strip()

    eerdere = (
        await session.scalars(
            select(Bericht)
            .where(Bericht.gesprek_id == gesprek.id)
            .order_by(Bericht.created_at.desc())
            .limit(settings.history_messages)
        )
    ).all()
    geschiedenis = [(b.rol, b.inhoud) for b in reversed(eerdere)]

    session.add(Bericht(gesprek_id=gesprek.id, rol="user", inhoud=vraag, bronnen=[]))
    if gesprek.titel == NIEUW_GESPREK:
        gesprek.titel = vraag[:80] + ("…" if len(vraag) > 80 else "")
    await session.commit()

    gesprek_id, kennisbank_id = gesprek.id, gesprek.kennisbank_id

    async def stream():
        antwoord: list[str] = []
        bronnen_json: list[dict] = []
        try:
            # Een vervolgvraag ('en voor deeltijders?') vindt zelf weinig; zoek daarom met een
            # versie die het onderwerp uit het gesprek meeneemt.
            zoekvraag = await herschrijf(chatmodel, vraag, geschiedenis) if geschiedenis else vraag
            vector = await embed_query(ollama, zoekvraag)
            async with SessionLocal() as s:
                bronnen = await zoek(
                    s,
                    kennisbank_id,
                    zoekvraag,
                    vector,
                    settings.retrieval_candidates,
                    settings.retrieval_top_k,
                )
            bronnen_json = [b.as_dict(i) for i, b in enumerate(bronnen, start=1)]
            yield _sse("bronnen", bronnen_json)

            async with antwoord_agent.run_stream(
                vraag_met_bronnen(vraag, bronnen),
                message_history=als_berichten(geschiedenis),
                model=chatmodel,
            ) as resultaat:
                async for token in resultaat.stream_text(delta=True, debounce_by=None):
                    antwoord.append(token)
                    yield _sse("token", token)
        except (AgentRunError, OllamaError) as e:
            log.warning("Fout van het taalmodel: %s", e)
            yield _sse("fout", {"detail": f"Het taalmodel gaf een fout: {e}"})
            return
        except Exception:
            log.exception("Antwoord genereren mislukt")
            yield _sse("fout", {"detail": "Er ging iets mis bij het maken van het antwoord."})
            return

        async with SessionLocal() as s:
            bericht = Bericht(
                gesprek_id=gesprek_id,
                rol="assistant",
                inhoud="".join(antwoord),
                bronnen=bronnen_json,
            )
            s.add(bericht)
            await s.commit()
            yield _sse("klaar", {"berichtId": str(bericht.id)})

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
