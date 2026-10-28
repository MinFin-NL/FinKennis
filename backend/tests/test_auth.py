"""OIDC-modus: tokens worden lokaal ondertekend; de JWKS-ophaalstap is vervangen."""

import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from app.config import Settings, get_settings

ISSUER = "http://keycloak.test/realms/finkennis"
AUDIENCE = "finkennis-api"
_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def token(sub: str, **extra) -> str:
    claims = {"sub": sub, "iss": ISSUER, "aud": AUDIENCE, "exp": int(time.time()) + 300}
    claims.update(extra)
    return jwt.encode(claims, _KEY, algorithm="RS256")


def auth(sub: str) -> dict:
    return {"Authorization": f"Bearer {token(sub)}"}


@pytest.fixture
def oidc(app):
    settings = Settings(
        **{**get_settings().model_dump(), "auth_mode": "oidc", "oidc_issuer": ISSUER}
    )
    app.dependency_overrides[get_settings] = lambda: settings

    async def signing_key(_token, _settings):
        return _KEY.public_key()

    origineel = app.state.signing_key
    app.state.signing_key = signing_key
    yield
    app.state.signing_key = origineel


async def test_zonder_token_401(client, oidc):
    r = await client.get("/api/v1/kennisbanken")
    assert r.status_code == 401
    assert r.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize(
    "claims",
    [
        {"aud": "iets-anders"},
        {"iss": "http://evil.test"},
        {"exp": int(time.time()) - 10},
    ],
)
async def test_ongeldig_token_401(client, oidc, claims):
    r = await client.get(
        "/api/v1/kennisbanken", headers={"Authorization": f"Bearer {token('anna', **claims)}"}
    )
    assert r.status_code == 401


async def test_gebruikers_zien_alleen_hun_eigen_kennisbanken(client, oidc):
    r = await client.post("/api/v1/kennisbanken", json={"naam": "Van Anna"}, headers=auth("anna"))
    kb_id = r.json()["id"]

    assert (await client.get("/api/v1/kennisbanken", headers=auth("bram"))).json() == []
    for methode, pad in [
        ("GET", f"/api/v1/kennisbanken/{kb_id}"),
        ("DELETE", f"/api/v1/kennisbanken/{kb_id}"),
        ("GET", f"/api/v1/kennisbanken/{kb_id}/documenten"),
        ("POST", f"/api/v1/kennisbanken/{kb_id}/gesprekken"),
    ]:
        r = await client.request(methode, pad, headers=auth("bram"), json={})
        assert r.status_code == 404, (methode, pad)

    gesprek = (
        await client.post(f"/api/v1/kennisbanken/{kb_id}/gesprekken", json={}, headers=auth("anna"))
    ).json()
    r = await client.get(f"/api/v1/gesprekken/{gesprek['id']}", headers=auth("bram"))
    assert r.status_code == 404
    r = await client.get(f"/api/v1/gesprekken/{gesprek['id']}", headers=auth("anna"))
    assert r.status_code == 200
