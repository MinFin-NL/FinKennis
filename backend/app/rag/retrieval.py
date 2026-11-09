"""Hybride zoeken: semantisch (pgvector) en op trefwoorden (Postgres full-text, Nederlands),
samengevoegd met Reciprocal Rank Fusion. Een derde ranglijst komt via de inzichten: een vaag
geformuleerde vraag lijkt vaak meer op een inzicht dan op de letterlijke tekst, en dan tellen
de fragmenten waar dat inzicht op steunt mee."""

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import TypeVar

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Chunk, Document, Inzicht

RRF_K = 60

T = TypeVar("T")


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


async def zoek_per_document(
    session: AsyncSession,
    kennisbank_id: uuid.UUID,
    vraag_vector: list[float],
    documenten: int = 4,
    per_document: int = 2,
) -> list[Bron]:
    """De beste fragmenten per document, uit de documenten die het best bij de vraag passen.

    Gewoon zoeken geeft de beste fragmenten van de hele kennisbank, en die komen vaak uit één
    document. Om documenten te vergelijken is per document de tekst over het onderwerp nodig.
    De documenten staan op volgorde van hun beste fragment; het resultaat per document bij
    elkaar. Dit zoekt exact (zonder HNSW-index), over alle fragmenten van de kennisbank."""
    if documenten <= 0 or per_document <= 0:
        return []
    afstand = Chunk.embedding.cosine_distance(vraag_vector)
    gerangschikt = (
        select(
            Chunk.id,
            Chunk.document_id,
            afstand.label("afstand"),
            func.row_number().over(partition_by=Chunk.document_id, order_by=afstand).label("rang"),
        )
        .where(Chunk.kennisbank_id == kennisbank_id)
        .subquery()
    )
    rows = (
        await session.execute(
            select(gerangschikt.c.id, gerangschikt.c.document_id, gerangschikt.c.afstand)
            .where(gerangschikt.c.rang <= per_document)
            .order_by(gerangschikt.c.afstand)
        )
    ).all()
    # Op afstand gesorteerd, dus de eerste keer dat een document voorkomt is zijn beste fragment.
    beste_documenten = list(dict.fromkeys(r.document_id for r in rows))[:documenten]
    gekozen = per_document_bij_elkaar(
        [r for r in rows if r.document_id in beste_documenten], lambda r: r.document_id
    )
    return await _bronnen(session, [r.id for r in gekozen], {})


async def bronnen_bij(session: AsyncSession, chunk_ids: list[uuid.UUID]) -> list[Bron]:
    """De fragmenten met deze ids, in deze volgorde. Wat niet meer bestaat (document
    verwijderd), valt weg."""
    return await _bronnen(session, chunk_ids, {})


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


def per_document_bij_elkaar(items: list[T], document: Callable[[T], uuid.UUID]) -> list[T]:
    """Zet items van hetzelfde document bij elkaar, in de volgorde waarin elk document voor
    het eerst voorkomt; binnen een document blijft de volgorde gelijk."""
    rang = {doc: n for n, doc in enumerate(dict.fromkeys(document(i) for i in items))}
    return sorted(items, key=lambda i: rang[document(i)])


def spreid_over_documenten(
    geordend: list[uuid.UUID],
    document_van: dict[uuid.UUID, uuid.UUID],
    limiet: int,
    per_document: int,
) -> list[uuid.UUID]:
    """Kiest de beste `limiet` uit `geordend` (beste eerst), maar hooguit `per_document` per
    document, zodat één groot document niet alle plekken vult en er iets te vergelijken valt.
    Blijven er plekken over (weinig documenten), dan vullen de overige ze alsnog.

    Het resultaat staat per document bij elkaar (in de volgorde waarin elk document voor het
    eerst voorkomt), en binnen een document op volgorde van `geordend`."""
    gekozen: list[uuid.UUID] = []
    over: list[uuid.UUID] = []
    telling: dict[uuid.UUID, int] = {}
    for iid in geordend:
        if len(gekozen) == limiet:
            break
        doc = document_van[iid]
        if telling.get(doc, 0) < per_document:
            gekozen.append(iid)
            telling[doc] = telling.get(doc, 0) + 1
        else:
            over.append(iid)
    gekozen += over[: limiet - len(gekozen)]
    return per_document_bij_elkaar(gekozen, document_van.__getitem__)


async def zoek_inzichten(
    session: AsyncSession,
    kennisbank_id: uuid.UUID,
    vraag_vector: list[float],
    limiet: int = 25,
    kandidaten: int = 60,
    per_document: int = 6,
) -> list[GevondenInzicht]:
    """Inzichten die bij de vraag passen. Een algemene vraag ('wat valt op?') lijkt op geen
    enkel inzicht in het bijzonder; daarom telt het belang even zwaar als de gelijkenis.
    Ze komen per document bij elkaar terug, uit zoveel mogelijk documenten, zodat het model
    verbanden tussen documenten kan zien."""
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
    if not scores:
        return []

    inzichten = {
        i.id: i for i in await session.scalars(select(Inzicht).where(Inzicht.id.in_(list(scores))))
    }
    geordend = sorted(
        (iid for iid in scores if iid in inzichten), key=scores.__getitem__, reverse=True
    )
    beste = spreid_over_documenten(
        geordend, {iid: i.document_id for iid, i in inzichten.items()}, limiet, per_document
    )
    eerste = {iid: inzichten[iid].chunk_ids[0] for iid in beste if inzichten[iid].chunk_ids}
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
