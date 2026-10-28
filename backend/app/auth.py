"""Wie is de gebruiker?

AUTH_MODE=none: lokaal ontwikkelen, iedereen is dezelfde dev-gebruiker.
AUTH_MODE=oidc: een bearer-token van Keycloak (of een andere OIDC-provider) is verplicht.

Er zijn twee rollen. Iedereen die inlogt is gebruiker: eigen kennisbanken en gesprekken.
De realm-rol 'beheerder' mag daarnaast gebruikers beheren. Rollen komen uit de claim
realm_access.roles van het access token; dat leeft vijf minuten, dus een gewijzigde rol
telt binnen vijf minuten.
"""

import asyncio
from dataclasses import dataclass
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, Request

from app.config import Settings, get_settings

DEV_SUB = "local-dev"
BEHEERDER = "beheerder"


@dataclass(frozen=True)
class User:
    sub: str
    naam: str | None = None
    email: str | None = None
    rollen: frozenset[str] = frozenset()

    @property
    def beheerder(self) -> bool:
        return BEHEERDER in self.rollen


_jwks_clients: dict[str, jwt.PyJWKClient] = {}


def _jwks_client(issuer: str) -> jwt.PyJWKClient:
    if issuer not in _jwks_clients:
        # Keycloak publiceert de sleutels hier; PyJWKClient cachet ze.
        _jwks_clients[issuer] = jwt.PyJWKClient(
            f"{issuer.rstrip('/')}/protocol/openid-connect/certs", cache_keys=True, lifespan=3600
        )
    return _jwks_clients[issuer]


async def _signing_key(token: str, settings: Settings):
    client = _jwks_client(settings.oidc_issuer)
    return (await asyncio.to_thread(client.get_signing_key_from_jwt, token)).key


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(401, detail, headers={"WWW-Authenticate": "Bearer"})


async def current_user(
    request: Request, settings: Annotated[Settings, Depends(get_settings)]
) -> User:
    if settings.auth_mode == "none":
        # Lokaal ben je ook beheerder; gebruikersbeheer zelf vraagt wel om Keycloak.
        return User(sub=DEV_SUB, naam="Lokale gebruiker", rollen=frozenset({BEHEERDER}))

    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise _unauthorized("Een bearer-token is verplicht.")

    try:
        key = await request.app.state.signing_key(token, settings)
        claims = jwt.decode(
            token,
            key,
            algorithms=["RS256", "PS256", "ES256"],
            audience=settings.oidc_audience,
            issuer=settings.oidc_issuer,
            options={"require": ["exp", "iss", "sub"]},
        )
    except jwt.PyJWTError as e:
        raise _unauthorized(f"Ongeldig token: {e}") from e

    return User(
        sub=claims["sub"],
        naam=claims.get("name") or claims.get("preferred_username"),
        email=claims.get("email"),
        rollen=frozenset((claims.get("realm_access") or {}).get("roles") or []),
    )


CurrentUser = Annotated[User, Depends(current_user)]


def require_beheerder(user: CurrentUser) -> User:
    if not user.beheerder:
        raise HTTPException(403, "Alleen een beheerder mag dit.")
    return user


Beheerder = Annotated[User, Depends(require_beheerder)]
