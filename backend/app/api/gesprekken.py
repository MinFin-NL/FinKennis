import json
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.responses import StreamingResponse
from pydantic_ai.exceptions import AgentRunError
from pydantic_ai.models import Model
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.api.deps import EigenGesprek, EigenKennisbank, Session
from app.auth import CurrentUser
from app.config import Settings, get_settings
from app.db import SessionLocal
from app.llm import EmbedClient, EmbedError
from app.models import Bericht, Document, DocumentStatus, Gesprek
from app.rag.embedding import embed_query
from app.rag.generation import (
    als_berichten,
    antwoord_agent,
    herschrijf,
    inzicht_agent,
    vraag_met_bronnen,
    vraag_met_inzichten,
)
from app.rag.retrieval import zoek, zoek_inzichten
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


async def _inzichten_onderweg(session, kennisbank_id) -> int:
    """Documenten die al doorzoekbaar zijn maar nog geen inzichten hebben."""
    return await session.scalar(
        select(func.count())
        .select_from(Document)
        .where(
            Document.kennisbank_id == kennisbank_id,
            Document.status == DocumentStatus.gereed,
            Document.inzichten_status.in_([DocumentStatus.wachtrij, DocumentStatus.verwerken]),
        )
    )


def _documenten(n: int) -> str:
    return "1 document" if n == 1 else f"{n} documenten"


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
    of `fout`.

    Met modus `inzichten` kiest de assistent uit de inzichten die vooraf uit de hele
    documenten zijn gehaald, in plaats van te zoeken in losse fragmenten."""
    embedder: EmbedClient = request.app.state.embedder
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

    modus = body.modus
    session.add(Bericht(gesprek_id=gesprek.id, rol="user", modus=modus, inhoud=vraag, bronnen=[]))
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
            vector = await embed_query(embedder, zoekvraag)
            onderweg = 0
            async with SessionLocal() as s:
                if modus == "inzichten":
                    inzichten = await zoek_inzichten(
                        s, kennisbank_id, vector, settings.inzichten_in_antwoord
                    )
                    bronnen = [g.bron for g in inzichten]
                    onderweg = await _inzichten_onderweg(s, kennisbank_id)
                else:
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

            if modus == "inzichten" and not inzichten:
                # Zonder inzichten valt er niets te kiezen; het model zou alleen gissen.
                melding = (
                    f"De inzichten voor {_documenten(onderweg)} worden nog gemaakt. Dat kan "
                    "een paar minuten duren; probeer het daarna opnieuw."
                    if onderweg
                    else "Er zijn nog geen inzichten in deze kennisbank. Ze worden gemaakt "
                    "zodra er documenten zijn verwerkt. Stel je vraag intussen als gewone vraag."
                )
                antwoord.append(melding)
                yield _sse("token", melding)
            else:
                agent, prompt = (
                    (inzicht_agent, vraag_met_inzichten(vraag, inzichten))
                    if modus == "inzichten"
                    else (antwoord_agent, vraag_met_bronnen(vraag, bronnen))
                )
                async with agent.run_stream(
                    prompt, message_history=als_berichten(geschiedenis), model=chatmodel
                ) as resultaat:
                    async for token in resultaat.stream_text(delta=True, debounce_by=None):
                        antwoord.append(token)
                        yield _sse("token", token)
                if onderweg:
                    noot = (
                        f"\n\nLet op: voor {_documenten(onderweg)} worden de inzichten nog "
                        "gemaakt. Die tellen hier nog niet mee."
                    )
                    antwoord.append(noot)
                    yield _sse("token", noot)
        except (AgentRunError, EmbedError) as e:
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
                modus=modus,
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
