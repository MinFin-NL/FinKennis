"""Verwerkt geüploade documenten op de achtergrond: parsen → chunken → embedden → opslaan.

De wachtrij is de document-tabel zelf. FOR UPDATE SKIP LOCKED zorgt dat meerdere workers
(of meerdere backend-instanties) nooit hetzelfde document oppakken.
"""

import asyncio
import logging
from pathlib import Path

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.config import Settings
from app.llm import EmbedClient
from app.models import Chunk, Document, DocumentStatus
from app.rag.chunking import chunk_document
from app.rag.embedding import embed_documents
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


async def run_worker(
    sessionmaker: async_sessionmaker, embedder: EmbedClient, settings: Settings
) -> None:
    while True:
        try:
            doc = await claim_next(sessionmaker)
        except Exception:
            log.exception("Wachtrij lezen mislukt")
            doc = None
        if doc is None:
            await asyncio.sleep(POLL_SECONDS)
            continue
        await process(doc, sessionmaker, embedder, settings)
