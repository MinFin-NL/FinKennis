"""Verwerkt geüploade documenten op de achtergrond: parsen → chunken → embedden → opslaan.
Daarna, als aparte stap, de inzichten: het hele document lezen (zie app.rag.inzichten).

De wachtrij is de document-tabel zelf. FOR UPDATE SKIP LOCKED zorgt dat meerdere workers
(of meerdere backend-instanties) nooit hetzelfde document oppakken.
"""

import asyncio
import logging
from pathlib import Path

from pydantic_ai.models import Model
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.config import Settings
from app.llm import EmbedClient
from app.models import Chunk, Document, DocumentStatus, Inzicht
from app.rag.chunking import chunk_document
from app.rag.embedding import embed_documents
from app.rag.inzichten import Fragment, Tussenstand, maak_inzichten, naar_json, uit_json
from app.rag.parsing import parse

log = logging.getLogger(__name__)
POLL_SECONDS = 2.0
MAX_POGINGEN = 3


async def claim_next(sessionmaker: async_sessionmaker) -> Document | None:
    async with sessionmaker() as session, session.begin():
        doc = await session.scalar(
            select(Document)
            .where(Document.status == DocumentStatus.wachtrij)
            .order_by(Document.created_at)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        if doc:
            doc.status = DocumentStatus.verwerken
            doc.pogingen += 1
        return doc


async def process(
    doc: Document, sessionmaker: async_sessionmaker, embedder: EmbedClient, settings: Settings
) -> None:
    try:
        dl_doc = await asyncio.to_thread(parse, Path(doc.pad), doc.bestandsnaam)
        chunks = await asyncio.to_thread(chunk_document, dl_doc, settings.chunk_max_tokens)
        if not chunks:
            raise ValueError("Er is geen tekst in het document gevonden.")
        vectoren = await embed_documents(
            embedder, [c.context_tekst for c in chunks], settings.embed_batch_size
        )

        async with sessionmaker() as session, session.begin():
            session.add_all(
                Chunk(
                    document_id=doc.id,
                    kennisbank_id=doc.kennisbank_id,
                    volgnummer=i,
                    tekst=c.tekst,
                    kopjes=c.kopjes,
                    pagina=c.pagina,
                    embedding=v,
                )
                for i, (c, v) in enumerate(zip(chunks, vectoren, strict=True))
            )
            await session.execute(
                update(Document)
                .where(Document.id == doc.id)
                .values(status=DocumentStatus.gereed, aantal_chunks=len(chunks), foutmelding=None)
            )
        log.info("Document %s verwerkt: %d chunks", doc.bestandsnaam, len(chunks))
    except Exception as e:
        log.exception("Verwerken van %s mislukt", doc.bestandsnaam)
        async with sessionmaker() as session, session.begin():
            await session.execute(
                update(Document)
                .where(Document.id == doc.id)
                .values(status=DocumentStatus.fout, foutmelding=str(e)[:1000])
            )


async def claim_next_inzichten(sessionmaker: async_sessionmaker) -> Document | None:
    async with sessionmaker() as session, session.begin():
        doc = await session.scalar(
            select(Document)
            .where(
                Document.status == DocumentStatus.gereed,
                Document.inzichten_status == DocumentStatus.wachtrij,
            )
            # Kleine documenten eerst: die zijn snel klaar, zo zie je snel de eerste inzichten.
            .order_by(Document.aantal_chunks, Document.created_at)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        if doc:
            doc.inzichten_status = DocumentStatus.verwerken
        return doc


async def process_inzichten(
    doc: Document,
    sessionmaker: async_sessionmaker,
    embedder: EmbedClient,
    chatmodel: Model,
    settings: Settings,
) -> None:
    try:
        async with sessionmaker() as session:
            chunks = (
                await session.scalars(
                    select(Chunk).where(Chunk.document_id == doc.id).order_by(Chunk.volgnummer)
                )
            ).all()
        fragmenten = [Fragment(c.id, c.tekst, c.kopjes or [], c.pagina) for c in chunks]

        # Een tussenstand telt alleen als hij met dezelfde sectiegrootte is gemaakt.
        sectie_tokens = settings.inzichten_sectie_tokens
        eerder = doc.inzichten_tussenstand or {}
        al_gelezen: Tussenstand = (
            {int(i): uit_json(b) for i, b in eerder.get("secties", {}).items()}
            if eerder.get("sectie_tokens") == sectie_tokens
            else {}
        )

        async def voortgang(totaal: int, gelezen: Tussenstand) -> None:
            async with sessionmaker() as session, session.begin():
                await session.execute(
                    update(Document)
                    .where(Document.id == doc.id)
                    .values(
                        inzichten_secties_totaal=totaal,
                        inzichten_secties_klaar=len(gelezen),
                        inzichten_tussenstand={
                            "sectie_tokens": sectie_tokens,
                            "secties": {str(i): naar_json(b) for i, b in gelezen.items()},
                        },
                    )
                )

        if al_gelezen:
            log.info("Inzichten voor %s: verder na %d secties", doc.bestandsnaam, len(al_gelezen))
        inzichten = await maak_inzichten(
            chatmodel,
            doc.bestandsnaam,
            fragmenten,
            sectie_tokens,
            settings.inzichten_per_document,
            settings.inzichten_gelijktijdig,
            al_gelezen,
            voortgang,
        )
        vectoren = await embed_documents(
            embedder, [f"{i.thema}: {i.tekst}" for i in inzichten], settings.embed_batch_size
        )

        async with sessionmaker() as session, session.begin():
            await session.execute(delete(Inzicht).where(Inzicht.document_id == doc.id))
            session.add_all(
                Inzicht(
                    document_id=doc.id,
                    kennisbank_id=doc.kennisbank_id,
                    volgnummer=n,
                    thema=i.thema[:200],
                    soort=i.soort,
                    belang=i.belang,
                    tekst=i.tekst,
                    chunk_ids=i.chunk_ids,
                    embedding=v,
                )
                for n, (i, v) in enumerate(zip(inzichten, vectoren, strict=True))
            )
            await session.execute(
                update(Document)
                .where(Document.id == doc.id)
                .values(
                    inzichten_status=DocumentStatus.gereed,
                    aantal_inzichten=len(inzichten),
                    inzichten_foutmelding=None,
                    inzichten_tussenstand=None,
                )
            )
        log.info("Inzichten voor %s gemaakt: %d", doc.bestandsnaam, len(inzichten))
    except Exception as e:
        # Vaak tijdelijk (rate limit, time-out): nog eens proberen, tot MAX_POGINGEN.
        log.exception("Inzichten maken voor %s mislukt", doc.bestandsnaam)
        pogingen = doc.inzichten_pogingen + 1
        async with sessionmaker() as session, session.begin():
            await session.execute(
                update(Document)
                .where(Document.id == doc.id)
                .values(
                    inzichten_status=DocumentStatus.wachtrij
                    if pogingen < MAX_POGINGEN
                    else DocumentStatus.fout,
                    inzichten_pogingen=pogingen,
                    inzichten_foutmelding=str(e)[:1000],
                )
            )


async def requeue_stuck(sessionmaker: async_sessionmaker) -> None:
    """Na een herstart staan documenten mogelijk nog op 'verwerken'; zet ze terug in de wachtrij.

    Een document dat al MAX_POGINGEN keer is opgepakt, heeft de backend waarschijnlijk zelf
    laten crashen. Dat krijgt status 'fout', anders blijft het de backend herstarten.
    """
    async with sessionmaker() as session, session.begin():
        await session.execute(
            update(Document)
            .where(Document.status == DocumentStatus.verwerken)
            .where(Document.pogingen >= MAX_POGINGEN)
            .values(
                status=DocumentStatus.fout,
                foutmelding="Het verwerken is herhaaldelijk afgebroken. Het document is "
                "mogelijk te groot; probeer het op te splitsen.",
            )
        )
        await session.execute(
            update(Document)
            .where(Document.status == DocumentStatus.verwerken)
            .values(status=DocumentStatus.wachtrij)
        )
        # Inzichten maken laat de backend niet crashen; een herstart (ook --reload) is dus
        # geen mislukte poging. Gewoon opnieuw beginnen.
        await session.execute(
            update(Document)
            .where(Document.inzichten_status == DocumentStatus.verwerken)
            .values(inzichten_status=DocumentStatus.wachtrij)
        )


async def run_worker(
    sessionmaker: async_sessionmaker, embedder: EmbedClient, settings: Settings
) -> None:
    while True:
        try:
            if doc := await claim_next(sessionmaker):
                await process(doc, sessionmaker, embedder, settings)
                continue
        except Exception:
            log.exception("Wachtrij lezen mislukt")
        await asyncio.sleep(POLL_SECONDS)


async def run_inzichten_worker(
    sessionmaker: async_sessionmaker, embedder: EmbedClient, chatmodel: Model, settings: Settings
) -> None:
    """Een eigen lus naast run_worker: inzichten maken duurt minuten per document en mag
    nieuwe uploads niet ophouden."""
    while True:
        try:
            if doc := await claim_next_inzichten(sessionmaker):
                await process_inzichten(doc, sessionmaker, embedder, chatmodel, settings)
                continue
        except Exception:
            log.exception("Wachtrij voor inzichten lezen mislukt")
        await asyncio.sleep(POLL_SECONDS)
