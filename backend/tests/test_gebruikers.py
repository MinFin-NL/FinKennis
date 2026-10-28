"""Gebruikersbeheer: de Keycloak Admin API is nagebootst met een httpx.MockTransport."""

import json
import uuid

import httpx
import pytest
from test_auth import ISSUER, oidc, token  # noqa: F401  (oidc is een fixture)

from app.keycloak import KeycloakAdmin


class FakeKeycloak:
    def __init__(self):
        self.users: dict[str, dict] = {}
        self.rollen: dict[str, set[str]] = {"gebruiker": set(), "beheerder": set()}
        self.wachtwoorden: dict[str, dict] = {}

    def voeg_toe(self, id_: str, email: str, *rollen: str) -> None:
        self.users[id_] = {"id": id_, "username": email, "email": email, "enabled": True}
        for r in rollen:
            self.rollen[r].add(id_)

    def handle(self, req: httpx.Request) -> httpx.Response:
        pad = req.url.path
        if pad.endswith("/protocol/openid-connect/token"):
            return httpx.Response(200, json={"access_token": "beheer", "expires_in": 300})
        assert req.headers["authorization"] == "Bearer beheer"
        pad = pad.removeprefix("/admin/realms/finkennis")
        delen = pad.strip("/").split("/")
        body = json.loads(req.content) if req.content else None

        if delen[0] == "roles":
            naam = delen[1]
            if len(delen) == 3:
                return httpx.Response(200, json=[self.users[i] for i in self.rollen[naam]])
            return httpx.Response(200, json={"id": f"rol-{naam}", "name": naam})

        if pad == "/users" and req.method == "GET":
            return httpx.Response(200, json=list(self.users.values()))
        if pad == "/users" and req.method == "POST":
            if any(u["email"] == body["email"] for u in self.users.values()):
                return httpx.Response(409)
            id_ = str(uuid.uuid4())
            self.users[id_] = {"id": id_, **body}
            return httpx.Response(201, headers={"Location": f"{req.url}/{id_}"})

        id_ = delen[1]
        if id_ not in self.users:
            return httpx.Response(404)
        if len(delen) == 2:
            if req.method == "GET":
                return httpx.Response(200, json=self.users[id_])
            if req.method == "PUT":
                self.users[id_].update(body)
                return httpx.Response(204)
            if req.method == "DELETE":
                del self.users[id_]
                for leden in self.rollen.values():
                    leden.discard(id_)
                return httpx.Response(204)
        if delen[2] == "reset-password":
            self.wachtwoorden[id_] = body
            return httpx.Response(204)
        if delen[2:] == ["role-mappings", "realm"]:
            for rol in body:
                leden = self.rollen[rol["name"]]
                leden.add(id_) if req.method == "POST" else leden.discard(id_)
            return httpx.Response(204)
        raise AssertionError(f"onverwacht verzoek {req.method} {pad}")


@pytest.fixture
def kc(app, oidc):  # noqa: F811
    fake = FakeKeycloak()
    fake.voeg_toe("anna", "anna@example.org", "gebruiker", "beheerder")
    fake.voeg_toe("bram", "bram@example.org", "gebruiker")
    app.state.keycloak = KeycloakAdmin(
        ISSUER, "finkennis-admin", "geheim", transport=httpx.MockTransport(fake.handle)
    )
    yield fake
    app.state.keycloak = None


def als(sub: str, *rollen: str) -> dict:
    claims = {"email": f"{sub}@example.org", "realm_access": {"roles": list(rollen)}}
    return {"Authorization": f"Bearer {token(sub, **claims)}"}


ANNA = als("anna", "gebruiker", "beheerder")
BRAM = als("bram", "gebruiker")


async def test_mij_geeft_rol(client, kc):
    r = await client.get("/api/v1/mij", headers=ANNA)
    assert r.json() == {
        "sub": "anna",
        "naam": None,
        "email": "anna@example.org",
        "beheerder": True,
    }
    assert (await client.get("/api/v1/mij", headers=BRAM)).json()["beheerder"] is False


async def test_mij_zonder_auth_is_beheerder(client):
    r = await client.get("/api/v1/mij")
    assert r.json()["beheerder"] is True


async def test_gebruikersbeheer_zonder_keycloak_503(client):
    assert (await client.get("/api/v1/gebruikers")).status_code == 503


async def test_gewone_gebruiker_mag_niet_beheren(client, kc):
    for methode, pad in [
        ("GET", "/api/v1/gebruikers"),
        ("POST", "/api/v1/gebruikers"),
        ("PATCH", "/api/v1/gebruikers/anna"),
        ("POST", "/api/v1/gebruikers/anna/wachtwoord-reset"),
        ("DELETE", "/api/v1/gebruikers/anna"),
    ]:
        r = await client.request(methode, pad, headers=BRAM, json={})
        assert r.status_code == 403, (methode, pad)


async def test_lijst(client, kc):
    kc.voeg_toe("sa", "service-account-finkennis-admin")
    await client.post("/api/v1/kennisbanken", json={"naam": "Van Bram"}, headers=BRAM)

    r = await client.get("/api/v1/gebruikers", headers=ANNA)
    per_id = {g["id"]: g for g in r.json()}
    assert set(per_id) == {"anna", "bram"}
    assert per_id["anna"]["beheerder"] and per_id["anna"]["zelf"]
    assert not per_id["bram"]["beheerder"] and not per_id["bram"]["zelf"]
    assert per_id["bram"]["aantalKennisbanken"] == 1


async def test_aanmaken_met_tijdelijk_wachtwoord(client, kc):
    r = await client.post(
        "/api/v1/gebruikers",
        json={"voornaam": "Cas", "achternaam": "Smit", "email": "Cas@Example.org"},
        headers=ANNA,
    )
    assert r.status_code == 201
    id_ = r.json()["id"]
    assert kc.users[id_]["username"] == "cas@example.org"
    assert id_ in kc.rollen["gebruiker"] and id_ not in kc.rollen["beheerder"]
    assert kc.wachtwoorden[id_] == {
        "type": "password",
        "value": r.json()["tijdelijkWachtwoord"],
        "temporary": True,
    }

    r = await client.post(
        "/api/v1/gebruikers",
        json={"voornaam": "Cas", "achternaam": "Smit", "email": "cas@example.org"},
        headers=ANNA,
    )
    assert r.status_code == 409


async def test_ongeldig_emailadres(client, kc):
    r = await client.post(
        "/api/v1/gebruikers",
        json={"voornaam": "X", "achternaam": "Y", "email": "geen-adres"},
        headers=ANNA,
    )
    assert r.status_code == 422


async def test_rol_en_status_wijzigen(client, kc):
    r = await client.patch("/api/v1/gebruikers/bram", json={"beheerder": True}, headers=ANNA)
    assert r.status_code == 204
    assert "bram" in kc.rollen["beheerder"]

    await client.patch("/api/v1/gebruikers/bram", json={"actief": False}, headers=ANNA)
    assert kc.users["bram"]["enabled"] is False


@pytest.mark.parametrize(
    "methode, pad, body",
    [
        ("PATCH", "/api/v1/gebruikers/anna", {"actief": False}),
        ("PATCH", "/api/v1/gebruikers/anna", {"beheerder": False}),
        ("DELETE", "/api/v1/gebruikers/anna", None),
    ],
)
async def test_beheerder_kan_zichzelf_niet_buitensluiten(client, kc, methode, pad, body):
    r = await client.request(methode, pad, json=body, headers=ANNA)
    assert r.status_code == 400
    assert "anna" in kc.users and "anna" in kc.rollen["beheerder"]


async def test_verwijderen_ruimt_kennisbanken_op(client, kc):
    kb = (await client.post("/api/v1/kennisbanken", json={"naam": "B"}, headers=BRAM)).json()
    await client.post("/api/v1/kennisbanken", json={"naam": "A"}, headers=ANNA)

    r = await client.delete("/api/v1/gebruikers/bram", headers=ANNA)
    assert r.status_code == 204
    assert "bram" not in kc.users
    assert (await client.get(f"/api/v1/kennisbanken/{kb['id']}", headers=BRAM)).status_code == 404
    assert len((await client.get("/api/v1/kennisbanken", headers=ANNA)).json()) == 1


async def test_onbekende_gebruiker_404(client, kc):
    r = await client.post("/api/v1/gebruikers/niemand/wachtwoord-reset", headers=ANNA)
    assert r.status_code == 404
