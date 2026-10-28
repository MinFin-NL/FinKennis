"""Wie ben ik, en gebruikersbeheer voor beheerders.

Gebruikers staan in Keycloak; FinKennis bewaart zelf alleen hun sub als eigenaar van
kennisbanken en gesprekken. Een nieuwe gebruiker krijgt een tijdelijk wachtwoord en kiest bij
de eerste login een eigen wachtwoord. Daarna logt hij in via de gewone SSO-flow.
"""

import secrets
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import func, select

from app.api.deps import Session
from app.auth import BEHEERDER, Beheerder, CurrentUser, User, require_beheerder
from app.keycloak import KeycloakAdmin
from app.models import Document, Kennisbank
from app.schemas import GebruikerIn, GebruikerOut, GebruikerPatch, MijOut, TijdelijkWachtwoord
from app.storage import verwijder_bestanden

GEBRUIKER = "gebruiker"

mij_router = APIRouter(tags=["Gebruikers"])
router = APIRouter(
    prefix="/gebruikers", tags=["Gebruikersbeheer"], dependencies=[Depends(require_beheerder)]
)


@mij_router.get("/mij", response_model=MijOut)
async def mij(user: CurrentUser):
    return MijOut(sub=user.sub, naam=user.naam, email=user.email, beheerder=user.beheerder)


def keycloak(request: Request) -> KeycloakAdmin:
    kc = getattr(request.app.state, "keycloak", None)
    if kc is None:
        raise HTTPException(503, "Gebruikersbeheer werkt alleen met AUTH_MODE=oidc.")
    return kc


Keycloak = Annotated[KeycloakAdmin, Depends(keycloak)]


def _pad(gebruiker_id: str) -> str:
    return f"/users/{quote(gebruiker_id, safe='')}"


def _is_zelf(user: User, kc_user: dict) -> bool:
    # Ook op e-mail: na een herimport van de realm heeft hetzelfde account een nieuwe sub.
    email = (kc_user.get("email") or "").lower()
    return kc_user["id"] == user.sub or (bool(user.email) and email == user.email.lower())


async def _niet_zelf(kc: KeycloakAdmin, user: User, gebruiker_id: str, actie: str) -> None:
    resp = await kc.request("GET", _pad(gebruiker_id))
    if resp.status_code == 404:
        raise HTTPException(404, "Gebruiker niet gevonden.")
    if _is_zelf(user, resp.json()):
        raise HTTPException(400, f"Je kunt jezelf niet {actie}.")


async def _zet_tijdelijk_wachtwoord(kc: KeycloakAdmin, gebruiker_id: str) -> str:
    wachtwoord = secrets.token_urlsafe(9)
    resp = await kc.request(
        "PUT",
        f"{_pad(gebruiker_id)}/reset-password",
        json={"type": "password", "value": wachtwoord, "temporary": True},
    )
    if resp.status_code == 404:
        raise HTTPException(404, "Gebruiker niet gevonden.")
    if resp.status_code not in (200, 204):
        raise HTTPException(502, "Wachtwoord instellen is mislukt.")
    return wachtwoord


@router.get("", response_model=list[GebruikerOut])
async def lijst(user: Beheerder, kc: Keycloak, session: Session):
    resp = await kc.request("GET", "/users", params={"max": 500})
    if resp.status_code != 200:
        raise HTTPException(502, "Gebruikers ophalen is mislukt.")
    beheerders = await kc.request("GET", f"/roles/{BEHEERDER}/users", params={"max": 500})
    beheerder_ids = {u["id"] for u in beheerders.json()} if beheerders.status_code == 200 else set()
    aantallen = dict(
        (
            await session.execute(
                select(Kennisbank.owner_sub, func.count()).group_by(Kennisbank.owner_sub)
            )
        ).all()
    )
    return [
        GebruikerOut(
            id=u["id"],
            gebruikersnaam=u.get("username"),
            voornaam=u.get("firstName"),
            achternaam=u.get("lastName"),
            email=u.get("email"),
            actief=u.get("enabled", False),
            beheerder=u["id"] in beheerder_ids,
            zelf=_is_zelf(user, u),
            aantal_kennisbanken=aantallen.get(u["id"], 0),
        )
        for u in resp.json()
        # Service accounts zijn techniek, geen mensen.
        if not (u.get("username") or "").startswith("service-account-")
    ]


@router.post("", response_model=TijdelijkWachtwoord, status_code=status.HTTP_201_CREATED)
async def maak(body: GebruikerIn, kc: Keycloak, response: Response):
    email = body.email.strip().lower()
    resp = await kc.request(
        "POST",
        "/users",
        json={
            "username": email,
            "email": email,
            "firstName": body.voornaam.strip(),
            "lastName": body.achternaam.strip(),
            "enabled": True,
            "emailVerified": True,
        },
    )
    if resp.status_code == 409:
        raise HTTPException(409, "Er bestaat al een gebruiker met dit e-mailadres.")
    if resp.status_code != 201:
        raise HTTPException(502, "Gebruiker aanmaken is mislukt.")
    # Keycloak geeft het nieuwe id alleen in de Location-header.
    gebruiker_id = resp.headers.get("location", "").rstrip("/").rsplit("/", 1)[-1]
    if not gebruiker_id:
        raise HTTPException(502, "Keycloak gaf geen id voor de nieuwe gebruiker.")

    rollen = [await kc.realm_rol(GEBRUIKER)]
    if body.beheerder:
        rollen.append(await kc.realm_rol(BEHEERDER))
    await kc.request("POST", f"{_pad(gebruiker_id)}/role-mappings/realm", json=rollen)

    wachtwoord = await _zet_tijdelijk_wachtwoord(kc, gebruiker_id)
    response.headers["Location"] = f"/api/v1/gebruikers/{gebruiker_id}"
    # Het tijdelijke wachtwoord is alleen in dit antwoord te zien.
    return TijdelijkWachtwoord(id=gebruiker_id, tijdelijk_wachtwoord=wachtwoord)


@router.patch("/{gebruiker_id}", status_code=status.HTTP_204_NO_CONTENT)
async def wijzig(gebruiker_id: str, body: GebruikerPatch, user: Beheerder, kc: Keycloak):
    if body.actief is False:
        await _niet_zelf(kc, user, gebruiker_id, "deactiveren")
    if body.beheerder is False:
        await _niet_zelf(kc, user, gebruiker_id, "de beheerdersrol afnemen")

    if body.actief is not None:
        resp = await kc.request("PUT", _pad(gebruiker_id), json={"enabled": body.actief})
        if resp.status_code == 404:
            raise HTTPException(404, "Gebruiker niet gevonden.")
        if resp.status_code not in (200, 204):
            raise HTTPException(502, "Gebruiker bijwerken is mislukt.")
    if body.beheerder is not None:
        rol = await kc.realm_rol(BEHEERDER)
        resp = await kc.request(
            "POST" if body.beheerder else "DELETE",
            f"{_pad(gebruiker_id)}/role-mappings/realm",
            json=[rol],
        )
        if resp.status_code == 404:
            raise HTTPException(404, "Gebruiker niet gevonden.")
        if resp.status_code not in (200, 204):
            raise HTTPException(502, "Rol bijwerken is mislukt.")


@router.post("/{gebruiker_id}/wachtwoord-reset", response_model=TijdelijkWachtwoord)
async def wachtwoord_reset(gebruiker_id: str, kc: Keycloak):
    wachtwoord = await _zet_tijdelijk_wachtwoord(kc, gebruiker_id)
    return TijdelijkWachtwoord(id=gebruiker_id, tijdelijk_wachtwoord=wachtwoord)


@router.delete("/{gebruiker_id}", status_code=status.HTTP_204_NO_CONTENT)
async def verwijder(gebruiker_id: str, user: Beheerder, kc: Keycloak, session: Session):
    await _niet_zelf(kc, user, gebruiker_id, "verwijderen")
    resp = await kc.request("DELETE", _pad(gebruiker_id))
    if resp.status_code not in (200, 204):
        raise HTTPException(502, "Gebruiker verwijderen is mislukt.")

    # Pas opruimen als Keycloak de gebruiker kwijt is. Mislukt dat, dan staat alles er nog
    # en kan de beheerder het opnieuw proberen. Gesprekken en fragmenten gaan mee via CASCADE.
    paden = (
        await session.scalars(
            select(Document.pad)
            .join(Kennisbank, Kennisbank.id == Document.kennisbank_id)
            .where(Kennisbank.owner_sub == gebruiker_id)
        )
    ).all()
    for kb in await session.scalars(select(Kennisbank).where(Kennisbank.owner_sub == gebruiker_id)):
        await session.delete(kb)
    await session.commit()
    verwijder_bestanden(paden)
