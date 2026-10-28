"""Foutafhandeling volgens RFC 9457 (application/problem+json), zoals de NL GOV API Design
Rules vragen."""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

PROBLEM_JSON = "application/problem+json"

_TITELS = {
    400: "Ongeldig verzoek",
    401: "Niet geauthenticeerd",
    403: "Geen toegang",
    404: "Niet gevonden",
    409: "Conflict",
    413: "Bestand te groot",
    415: "Bestandstype niet ondersteund",
    422: "Ongeldige invoer",
    500: "Interne fout",
    502: "Fout bij een achterliggende dienst",
    503: "Dienst niet beschikbaar",
}


def problem(status: int, detail: str | None = None, **extra) -> JSONResponse:
    body = {"type": "about:blank", "title": _TITELS.get(status, "Fout"), "status": status}
    if detail:
        body["detail"] = detail
    body.update(extra)
    return JSONResponse(body, status_code=status, media_type=PROBLEM_JSON)


def install_handlers(app: FastAPI) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def http_exc(request: Request, exc: StarletteHTTPException):
        resp = problem(exc.status_code, str(exc.detail) if exc.detail else None)
        if exc.headers:
            resp.headers.update(exc.headers)
        return resp

    @app.exception_handler(RequestValidationError)
    async def validation_exc(request: Request, exc: RequestValidationError):
        fouten = [
            {"name": ".".join(str(p) for p in e["loc"]), "reason": e["msg"]} for e in exc.errors()
        ]
        return problem(422, "De invoer is niet geldig.", invalidParams=fouten)
