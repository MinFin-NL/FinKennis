"""Hybride zoeken: semantisch (pgvector) en op trefwoorden (Postgres full-text, Nederlands),
samengevoegd met Reciprocal Rank Fusion. Een derde ranglijst komt via de inzichten: een vaag
geformuleerde vraag lijkt vaak meer op een inzicht dan op de letterlijke tekst, en dan tellen
de fragmenten waar dat inzicht op steunt mee."""

import uuid
from dataclasses import dataclass

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Chunk, Document, Inzicht

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

    via_inzichten = (
        await session.scalars(
            select(Inzicht.chunk_ids)
            .where(Inzicht.kennisbank_id == kennisbank_id)
            .order_by(Inzicht.embedding.cosine_distance(vraag_vector))
            .limit(kandidaten)
        )
    ).all()
    inzichtfragmenten = list(dict.fromkeys(ids[0] for ids in via_inzichten if ids))

    scores = rrf([list(semantisch), list(trefwoord), inzichtfragmenten])
    beste = sorted(scores, key=scores.__getitem__, reverse=True)[:top_k]
    return await _bronnen(session, beste, scores)


async def _bronnen(
    session: AsyncSession, beste: list[uuid.UUID], scores: dict[uuid.UUID, float]
) -> list[Bron]:
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
            score=scores.get(cid, 0.0),
        )
        for cid in beste
        if cid in per_id
    ]


@dataclass
class GevondenInzicht:
    thema: str
    soort: str
    belang: int
    tekst: str
    bron: Bron  # het eerste fragment waar het inzicht op steunt


async def zoek_inzichten(
    session: AsyncSession,
    kennisbank_id: uuid.UUID,
    vraag_vector: list[float],
    limiet: int = 25,
    kandidaten: int = 60,
) -> list[GevondenInzicht]:
    """Inzichten die bij de vraag passen. Een algemene vraag ('wat valt op?') lijkt op geen
    enkel inzicht in het bijzonder; daarom telt het belang even zwaar als de gelijkenis."""
    await session.execute(text("SET LOCAL hnsw.iterative_scan = relaxed_order"))
    op_gelijkenis = (
        await session.scalars(
            select(Inzicht.id)
            .where(Inzicht.kennisbank_id == kennisbank_id)
            .order_by(Inzicht.embedding.cosine_distance(vraag_vector))
            .limit(kandidaten)
        )
    ).all()
    op_belang = (
        await session.scalars(
            select(Inzicht.id)
            .where(Inzicht.kennisbank_id == kennisbank_id)
            .order_by(Inzicht.belang.desc(), Inzicht.volgnummer, Inzicht.id)
            .limit(kandidaten)
        )
    ).all()
    scores = rrf([list(op_gelijkenis), list(op_belang)])
    beste = sorted(scores, key=scores.__getitem__, reverse=True)[:limiet]
    if not beste:
        return []

    inzichten = {
        i.id: i for i in await session.scalars(select(Inzicht).where(Inzicht.id.in_(beste)))
    }
    eerste = {iid: inzichten[iid].chunk_ids[0] for iid in beste if iid in inzichten}
    bronnen = {b.chunk_id: b for b in await _bronnen(session, list(set(eerste.values())), {})}
    return [
        GevondenInzicht(
            thema=inzichten[iid].thema,
            soort=inzichten[iid].soort,
            belang=inzichten[iid].belang,
            tekst=inzichten[iid].tekst,
            bron=bronnen[cid],
        )
        for iid, cid in eerste.items()
        if cid in bronnen
    ]
