import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from app.models import DocumentStatus


class Schema(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, from_attributes=True)


class KennisbankIn(Schema):
    naam: str = Field(min_length=1, max_length=200)
    omschrijving: str = Field(default="", max_length=2000)


class KennisbankPatch(Schema):
    naam: str | None = Field(default=None, min_length=1, max_length=200)
    omschrijving: str | None = Field(default=None, max_length=2000)


class KennisbankOut(Schema):
    id: uuid.UUID
    naam: str
    omschrijving: str
    created_at: datetime
    aantal_documenten: int = 0


class DocumentOut(Schema):
    id: uuid.UUID
    bestandsnaam: str
    mime: str
    grootte: int
    status: DocumentStatus
    foutmelding: str | None
    aantal_chunks: int
    created_at: datetime


class UploadResultaat(Schema):
    toegevoegd: list[DocumentOut]
    overgeslagen: list[str] = Field(description="Bestanden die al in de kennisbank stonden")


class GesprekIn(Schema):
    titel: str | None = Field(default=None, max_length=200)


class BerichtIn(Schema):
    inhoud: str = Field(min_length=1, max_length=4000)


class BerichtOut(Schema):
    id: uuid.UUID
    rol: str
    inhoud: str
    bronnen: list[dict]
    created_at: datetime


class GesprekOut(Schema):
    id: uuid.UUID
    kennisbank_id: uuid.UUID
    titel: str
    created_at: datetime


class GesprekDetail(GesprekOut):
    berichten: list[BerichtOut]


class MijOut(Schema):
    sub: str
    naam: str | None
    email: str | None
    beheerder: bool


class GebruikerOut(Schema):
    id: str
    gebruikersnaam: str | None
    voornaam: str | None
    achternaam: str | None
    email: str | None
    actief: bool
    beheerder: bool
    zelf: bool
    aantal_kennisbanken: int


class GebruikerIn(Schema):
    voornaam: str = Field(min_length=1, max_length=100)
    achternaam: str = Field(min_length=1, max_length=100)
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$", max_length=254)
    beheerder: bool = False


class GebruikerPatch(Schema):
    actief: bool | None = None
    beheerder: bool | None = None


class TijdelijkWachtwoord(Schema):
    id: str
    tijdelijk_wachtwoord: str
