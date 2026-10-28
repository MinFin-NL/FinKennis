import uuid
from typing import Annotated

from fastapi import Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import CurrentUser
from app.db import get_session
from app.models import Gesprek, Kennisbank

Session = Annotated[AsyncSession, Depends(get_session)]


async def eigen_kennisbank(
    kennisbank_id: uuid.UUID, user: CurrentUser, session: Session
) -> Kennisbank:
    # Een kennisbank van een ander geeft 404, niet 403: we verraden niet dat hij bestaat.
    kb = await session.scalar(
        select(Kennisbank).where(Kennisbank.id == kennisbank_id, Kennisbank.owner_sub == user.sub)
    )
    if kb is None:
        raise HTTPException(404, "Kennisbank niet gevonden.")
    return kb


async def eigen_gesprek(gesprek_id: uuid.UUID, user: CurrentUser, session: Session) -> Gesprek:
    gesprek = await session.scalar(
        select(Gesprek).where(Gesprek.id == gesprek_id, Gesprek.owner_sub == user.sub)
    )
    if gesprek is None:
        raise HTTPException(404, "Gesprek niet gevonden.")
    return gesprek


EigenKennisbank = Annotated[Kennisbank, Depends(eigen_kennisbank)]
EigenGesprek = Annotated[Gesprek, Depends(eigen_gesprek)]
