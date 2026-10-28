"""Hybride zoeken: semantisch (pgvector) en op trefwoorden (Postgres full-text, Nederlands),
samengevoegd met Reciprocal Rank Fusion."""

import uuid
from dataclasses import dataclass

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Chunk, Document

RRF_K = 60


@dataclass
class Bron:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    bestandsnaam: str
    pagina: int | None
    kopjes: list[str]
    tekst: str
    score: float

    def as_dict(self, nummer: int) -> dict:
        return {
            "nummer": nummer,
            "chunkId": str(self.chunk_id),
            "documentId": str(self.document_id),
            "bestandsnaam": self.bestandsnaam,
            "pagina": self.pagina,
            "kopjes": self.kopjes,
            "fragment": self.tekst[:400],
        }


def rrf(rankings: list[list[uuid.UUID]], k: int = RRF_K) -> dict[uuid.UUID, float]:
    scores: dict[uuid.UUID, float] = {}
    for ranking in rankings:
        for rang, cid in enumerate(ranking):
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rang + 1)
    return scores


async def zoek(
    session: AsyncSession,
    kennisbank_id: uuid.UUID,
    vraag: str,
    vraag_vector: list[float],
    kandidaten: int = 20,
    top_k: int = 6,
) -> list[Bron]:
    # Met een filter op kennisbank kan HNSW te weinig treffers opleveren; pgvector >= 0.8 zoekt
    # dan verder in de index in plaats van een te korte lijst terug te geven.
    await session.execute(text("SET LOCAL hnsw.iterative_scan = relaxed_order"))
    semantisch = (
        await session.scalars(
            select(Chunk.id)
            .where(Chunk.kennisbank_id == kennisbank_id)
            .order_by(Chunk.embedding.cosine_distance(vraag_vector))
            .limit(kandidaten)
        )
    ).all()

    tsquery = func.websearch_to_tsquery("dutch", vraag)
    trefwoord = (
        await session.scalars(
            select(Chunk.id)
            .where(Chunk.kennisbank_id == kennisbank_id, Chunk.tsv.op("@@")(tsquery))
            .order_by(func.ts_rank_cd(Chunk.tsv, tsquery).desc())
            .limit(kandidaten)
        )
    ).all()

    scores = rrf([list(semantisch), list(trefwoord)])
    beste = sorted(scores, key=scores.__getitem__, reverse=True)[:top_k]
    if not beste:
        return []

    rows = (
        await session.execute(
            select(Chunk, Document.bestandsnaam)
            .join(Document, Document.id == Chunk.document_id)
            .where(Chunk.id.in_(beste))
        )
    ).all()
    per_id = {c.id: (c, naam) for c, naam in rows}
    return [
        Bron(
            chunk_id=cid,
            document_id=per_id[cid][0].document_id,
            bestandsnaam=per_id[cid][1],
            pagina=per_id[cid][0].pagina,
            kopjes=per_id[cid][0].kopjes or [],
            tekst=per_id[cid][0].tekst,
            score=scores[cid],
        )
        for cid in beste
        if cid in per_id
    ]
