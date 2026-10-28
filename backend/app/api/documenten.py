import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select

from app.api.deps import EigenKennisbank, Session
from app.config import Settings, get_settings
from app.models import Document
from app.rag.parsing import ONDERSTEUNDE_EXTENSIES
from app.schemas import DocumentOut, UploadResultaat
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
