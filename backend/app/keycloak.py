"""Client voor de Keycloak Admin REST API, voor gebruikersbeheer.

De backend logt in met een eigen confidential client met service account (client-credentials
grant). Dat service account heeft de realm-management-rollen manage-users, view-users en
view-realm nodig; de laatste om realm-rollen en hun leden te lezen.
"""

import asyncio
import time

import httpx
from fastapi import HTTPException


class KeycloakAdmin:
    def __init__(
        self,
        issuer: str,
        client_id: str,
        client_secret: str,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        # http://host/realms/finkennis → http://host/admin/realms/finkennis
        realm_url = issuer.rstrip("/")
        basis, _, realm = realm_url.rpartition("/realms/")
        self.token_url = f"{realm_url}/protocol/openid-connect/token"
        self.admin_url = f"{basis}/admin/realms/{realm}"
        self.client_id = client_id
        self.client_secret = client_secret
        self._http = httpx.AsyncClient(timeout=15, transport=transport)
        self._token: str | None = None
        self._verloopt = 0.0
        self._lock = asyncio.Lock()

    async def _admin_token(self) -> str:
        async with self._lock:
            if self._token and time.monotonic() < self._verloopt - 10:
                return self._token
            try:
                resp = await self._http.post(
                    self.token_url,
                    data={
                        "grant_type": "client_credentials",
                        "client_id": self.client_id,
                        "client_secret": self.client_secret,
                    },
                )
            except httpx.HTTPError as e:
                raise HTTPException(502, f"Keycloak is niet bereikbaar: {e}") from e
            if resp.status_code != 200:
                raise HTTPException(
                    502,
                    "Geen beheertoken van Keycloak gekregen. Controleer OIDC_ADMIN_CLIENT_ID en "
                    "OIDC_ADMIN_CLIENT_SECRET.",
                )
            data = resp.json()
            self._token = data["access_token"]
            self._verloopt = time.monotonic() + data.get("expires_in", 60)
            return self._token

    async def request(self, method: str, pad: str, **kwargs) -> httpx.Response:
        token = await self._admin_token()
        try:
            resp = await self._http.request(
                method,
                f"{self.admin_url}{pad}",
                headers={"Authorization": f"Bearer {token}"},
                **kwargs,
            )
        except httpx.HTTPError as e:
            raise HTTPException(502, f"Keycloak is niet bereikbaar: {e}") from e
        if resp.status_code == 403:
            raise HTTPException(
                502,
                "Het service account mist de rollen manage-users, view-users en view-realm.",
            )
        return resp

    async def realm_rol(self, naam: str) -> dict:
        resp = await self.request("GET", f"/roles/{naam}")
        if resp.status_code != 200:
            raise HTTPException(502, f"De realm-rol '{naam}' bestaat niet in Keycloak.")
        return resp.json()

    async def aclose(self) -> None:
        await self._http.aclose()
