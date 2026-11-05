import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select, update

from app.api.deps import EigenKennisbank, Session
from app.config import Settings, get_settings
from app.models import Chunk, Document, DocumentStatus, Inzicht
from app.rag.parsing import ONDERSTEUNDE_EXTENSIES
from app.schemas import DocumentOut, InzichtBron, InzichtOut, UploadResultaat
from app.storage import bewaar_upload, verwijder_bestanden

router = APIRouter(prefix="/kennisbanken/{kennisbank_id}/documenten", tags=["Documenten"])


@router.get("", response_model=list[DocumentOut])
async def lijst(kb: EigenKennisbank, session: Session):
    return (
        await session.scalars(
            select(Document)
            .where(Document.kennisbank_id == kb.id)
            .order_by(Document.created_at.desc())
        )
    ).all()


@router.post("", response_model=UploadResultaat, status_code=status.HTTP_202_ACCEPTED)
async def upload(
    kb: EigenKennisbank,
    session: Session,
    settings: Annotated[Settings, Depends(get_settings)],
    bestanden: Annotated[list[UploadFile], File(description="Een of meer documenten")],
):
    """Bestanden worden direct opgeslagen en daarna op de achtergrond verwerkt.
    Volg de status via GET op deze collectie."""
    for b in bestanden:
        ext = Path(b.filename or "").suffix.lower()
        if ext not in ONDERSTEUNDE_EXTENSIES:
            raise HTTPException(
                415,
                f"{b.filename}: bestandstype niet ondersteund. "
                f"Toegestaan: {', '.join(sorted(ONDERSTEUNDE_EXTENSIES))}.",
            )

    map_ = settings.upload_dir / str(kb.id)
    max_bytes = settings.max_upload_mb * 1024 * 1024
    bekend = set(
        (
            await session.scalars(select(Document.sha256).where(Document.kennisbank_id == kb.id))
        ).all()
    )

    toegevoegd: list[Document] = []
    overgeslagen: list[str] = []
    try:
        for b in bestanden:
            pad, sha, grootte = await bewaar_upload(b, map_, max_bytes)
            if sha in bekend:
                verwijder_bestanden([str(pad)])
                overgeslagen.append(b.filename or "")
                continue
            bekend.add(sha)
            doc = Document(
                kennisbank_id=kb.id,
                bestandsnaam=Path(b.filename or "document").name,
                mime=b.content_type or "",
                sha256=sha,
                grootte=grootte,
                pad=str(pad),
            )
            session.add(doc)
            toegevoegd.append(doc)
        await session.commit()
    except BaseException:
        await session.rollback()
        verwijder_bestanden([d.pad for d in toegevoegd])
        raise

    for d in toegevoegd:
        await session.refresh(d)
    return UploadResultaat(
        toegevoegd=[DocumentOut.model_validate(d) for d in toegevoegd], overgeslagen=overgeslagen
    )


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def verwijder(document_id: uuid.UUID, kb: EigenKennisbank, session: Session):
    doc = await session.scalar(
        select(Document).where(Document.id == document_id, Document.kennisbank_id == kb.id)
    )
    if doc is None:
        raise HTTPException(404, "Document niet gevonden.")
    pad = doc.pad
    await session.delete(doc)
    await session.commit()
    verwijder_bestanden([pad])


async def _eigen_document(document_id: uuid.UUID, kb, session) -> Document:
    doc = await session.scalar(
        select(Document).where(Document.id == document_id, Document.kennisbank_id == kb.id)
    )
    if doc is None:
        raise HTTPException(404, "Document niet gevonden.")
    return doc


@router.get("/{document_id}/inzichten", response_model=list[InzichtOut])
async def inzichten(document_id: uuid.UUID, kb: EigenKennisbank, session: Session):
    """De inzichten die uit het hele document zijn gehaald, belangrijkste eerst, met de
    fragmenten waar ze op steunen."""
    doc = await _eigen_document(document_id, kb, session)
    lijst = (
        await session.scalars(
            select(Inzicht).where(Inzicht.document_id == doc.id).order_by(Inzicht.volgnummer)
        )
    ).all()
    chunk_ids = {cid for i in lijst for cid in i.chunk_ids}
    chunks = {c.id: c for c in await session.scalars(select(Chunk).where(Chunk.id.in_(chunk_ids)))}
    return [
        InzichtOut(
            id=i.id,
            thema=i.thema,
            soort=i.soort,
            belang=i.belang,
            tekst=i.tekst,
            bronnen=[
                InzichtBron(
                    chunk_id=c.id, pagina=c.pagina, kopjes=c.kopjes or [], fragment=c.tekst[:400]
                )
                for cid in i.chunk_ids
                if (c := chunks.get(cid))
            ],
        )
        for i in lijst
    ]


@router.post(
    "/{document_id}/inzichten", response_model=DocumentOut, status_code=status.HTTP_202_ACCEPTED
)
async def maak_inzichten_opnieuw(document_id: uuid.UUID, kb: EigenKennisbank, session: Session):
    """Zet het document opnieuw in de wachtrij voor inzichten, bijvoorbeeld na een fout.
    De huidige inzichten blijven bruikbaar tot de nieuwe klaar zijn."""
    doc = await _eigen_document(document_id, kb, session)
    if doc.status != DocumentStatus.gereed:
        raise HTTPException(409, "Het document moet eerst verwerkt zijn.")
    if doc.inzichten_status == DocumentStatus.verwerken:
        raise HTTPException(409, "De inzichten worden al gemaakt.")
    await session.execute(
        update(Document)
        .where(Document.id == doc.id)
        .values(
            inzichten_status=DocumentStatus.wachtrij,
            inzichten_pogingen=0,
            inzichten_foutmelding=None,
            inzichten_secties_klaar=0,
            inzichten_tussenstand=None,
        )
    )
    await session.commit()
    await session.refresh(doc)
    return doc
