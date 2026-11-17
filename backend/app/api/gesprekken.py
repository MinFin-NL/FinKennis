import json
import logging
import re
import uuid
from typing import Annotated

import openai
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
from app.llm import EmbedClient, EmbedError
from app.models import Bericht, Gesprek
from app.rag.embedding import embed_query
from app.rag.generation import (
    Context,
    als_berichten,
    antwoord_agent,
    herschrijf,
    vraag_met_context,
)
from app.rag.retrieval import (
    Bron,
    bronnen_bij,
    per_document_bij_elkaar,
    zoek,
    zoek_inzichten,
    zoek_per_document,
)
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


_BRONNUMMER = re.compile(r"\[(\d+)\]")


def _eerdere_bronnen(eerdere: list[Bericht], maximum: int) -> tuple[list[uuid.UUID], dict]:
    """De fragmenten waar eerdere antwoorden naar verwezen, nieuwste antwoord eerst, en per
    fragment het inzicht dat er toen bij hoorde. Alleen geciteerde bronnen: daar ging het
    antwoord over."""
    ids: list[uuid.UUID] = []
    inzichten: dict[uuid.UUID, str] = {}
    for b in eerdere:  # nieuwste eerst
        if b.rol != "assistant":
            continue
        geciteerd = {int(n) for n in _BRONNUMMER.findall(b.inhoud)}
        for bron in b.bronnen or []:
            if bron.get("nummer") not in geciteerd:
                continue
            cid = uuid.UUID(bron["chunkId"])
            if cid not in ids:
                ids.append(cid)
            if bron.get("inzicht"):
                inzichten.setdefault(cid, bron["inzicht"])
    return ids[:maximum], inzichten


def _samen(eerder: list[Bron], nieuw: list[Bron], maximum: int) -> list[Bron]:
    gezien: set[uuid.UUID] = set()
    uit = []
    for b in [*eerder, *nieuw]:
        if b.chunk_id not in gezien:
            gezien.add(b.chunk_id)
            uit.append(b)
    return uit[:maximum]


TE_DRUK = (
    "Het taalmodel is op dit moment te druk (te veel vragen tegelijk). "
    "Probeer het over een minuut opnieuw."
)


def _te_druk(e: Exception) -> bool:
    """Een rate limit (429), van het chatmodel of van de embeddings. De SDK heeft dan al een
    paar keer opnieuw geprobeerd."""
    if getattr(e, "status_code", None) == 429:  # ModelHTTPError / ModelRateLimitError
        return True
    return isinstance(e.__cause__, openai.RateLimitError)  # EmbedError


def _foutmelding(e: Exception) -> str:
    return TE_DRUK if _te_druk(e) else f"Het taalmodel gaf een fout: {e}"


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

    Er is één manier van vragen. De assistent krijgt steeds drie dingen: de bronnen waar
    eerdere antwoorden naar verwezen (zodat je kunt doorpraten), de fragmenten die bij de vraag
    gevonden worden, en de inzichten die vooraf uit de hele documenten zijn gehaald (voor wat
    er opvalt, ook over documenten heen). Feiten krijgen een bron; meedenken staat apart."""
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

    modus = "chat"
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
            ids, eerdere_inzichten = _eerdere_bronnen(eerdere, settings.chat_eerdere_bronnen)
            async with SessionLocal() as s:
                gevonden = await zoek(
                    s,
                    kennisbank_id,
                    zoekvraag,
                    vector,
                    settings.retrieval_candidates,
                    settings.retrieval_top_k,
                )
                per_document = await zoek_per_document(
                    s,
                    kennisbank_id,
                    vector,
                    settings.chat_documenten,
                    settings.chat_per_document,
                )
                # Eerst wat het vorige antwoord gebruikte, dan de beste treffers, dan de rest per
                # document; daarna per document bij elkaar, zodat ze te vergelijken zijn.
                fragmenten = per_document_bij_elkaar(
                    _samen(
                        await bronnen_bij(s, ids),
                        [*gevonden, *per_document],
                        settings.chat_max_fragmenten,
                    ),
                    lambda b: b.document_id,
                )
                inzichten = await zoek_inzichten(
                    s,
                    kennisbank_id,
                    vector,
                    settings.inzichten_in_antwoord,
                    per_document=settings.inzichten_per_document_in_antwoord,
                )
            ctx = Context(fragmenten, inzichten, eerdere_inzichten)
            bronnen_json = ctx.bronnen_json()
            yield _sse("bronnen", bronnen_json)

            async with antwoord_agent.run_stream(
                vraag_met_context(vraag, ctx),
                message_history=als_berichten(geschiedenis),
                model=chatmodel,
            ) as resultaat:
                async for token in resultaat.stream_text(delta=True, debounce_by=None):
                    antwoord.append(token)
                    yield _sse("token", token)
        except (AgentRunError, EmbedError) as e:
            log.warning("Fout van het taalmodel: %s", e)
            yield _sse("fout", {"detail": _foutmelding(e)})
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
