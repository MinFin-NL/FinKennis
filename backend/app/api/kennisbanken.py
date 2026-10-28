from fastapi import APIRouter, Response, status
from sqlalchemy import func, select

from app.api.deps import EigenKennisbank, Session
from app.auth import CurrentUser
from app.models import Document, Kennisbank
from app.schemas import KennisbankIn, KennisbankOut, KennisbankPatch
from app.storage import verwijder_bestanden

router = APIRouter(prefix="/kennisbanken", tags=["Kennisbanken"])


async def _aantal_documenten(session: Session, kb: Kennisbank) -> int:
    return await session.scalar(
        select(func.count()).select_from(Document).where(Document.kennisbank_id == kb.id)
    )


def _out(kb: Kennisbank, aantal: int) -> KennisbankOut:
    return KennisbankOut.model_validate(kb).model_copy(update={"aantal_documenten": aantal})


@router.get("", response_model=list[KennisbankOut])
async def lijst(user: CurrentUser, session: Session):
    rows = (
        await session.execute(
            select(Kennisbank, func.count(Document.id))
            .outerjoin(Document, Document.kennisbank_id == Kennisbank.id)
            .where(Kennisbank.owner_sub == user.sub)
            .group_by(Kennisbank.id)
            .order_by(Kennisbank.created_at.desc())
        )
    ).all()
    return [_out(kb, n) for kb, n in rows]


@router.post("", response_model=KennisbankOut, status_code=status.HTTP_201_CREATED)
async def maak(body: KennisbankIn, user: CurrentUser, session: Session, response: Response):
    kb = Kennisbank(owner_sub=user.sub, naam=body.naam, omschrijving=body.omschrijving)
    session.add(kb)
    await session.commit()
    await session.refresh(kb)
    response.headers["Location"] = f"/api/v1/kennisbanken/{kb.id}"
    return _out(kb, 0)


@router.get("/{kennisbank_id}", response_model=KennisbankOut)
async def lees(kb: EigenKennisbank, session: Session):
    return _out(kb, await _aantal_documenten(session, kb))


@router.patch("/{kennisbank_id}", response_model=KennisbankOut)
async def wijzig(body: KennisbankPatch, kb: EigenKennisbank, session: Session):
    for veld, waarde in body.model_dump(exclude_unset=True).items():
        if waarde is not None:
            setattr(kb, veld, waarde)
    await session.commit()
    await session.refresh(kb)
    return _out(kb, await _aantal_documenten(session, kb))


@router.delete("/{kennisbank_id}", status_code=status.HTTP_204_NO_CONTENT)
async def verwijder(kb: EigenKennisbank, session: Session):
    paden = (
        await session.scalars(select(Document.pad).where(Document.kennisbank_id == kb.id))
    ).all()
    await session.delete(kb)
    await session.commit()
    verwijder_bestanden(paden)
