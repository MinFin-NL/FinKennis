import asyncio
import logging
from contextlib import asynccontextmanager, suppress

import pydantic_ai
from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api import documenten, gebruikers, gesprekken, kennisbanken
from app.auth import _signing_key
from app.config import get_settings
from app.db import SessionLocal, engine
from app.errors import install_handlers
from app.keycloak import KeycloakAdmin
from app.llm.ollama import OllamaClient, chatmodel
from app.rag.ingest_worker import requeue_stuck, run_worker

# Geen welkomstbanner van Pydantic AI tussen de serverlogs.
pydantic_ai.BANNER_ENABLED = False

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

API_VERSION = "1.0.0"


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    app.state.ollama = OllamaClient(settings.ollama_url, settings.embed_model)
    app.state.chatmodel = chatmodel(settings.ollama_url, settings.chat_model)
    app.state.keycloak = None
    if settings.auth_mode == "oidc":
        app.state.keycloak = KeycloakAdmin(
            settings.oidc_issuer, settings.oidc_admin_client_id, settings.oidc_admin_client_secret
        )

    workers: list[asyncio.Task] = []
    if settings.ingest_worker_enabled:
        await requeue_stuck(SessionLocal)
        workers = [
            asyncio.create_task(run_worker(SessionLocal, app.state.ollama, settings))
            for _ in range(settings.ingest_concurrency)
        ]
    yield
    for w in workers:
        w.cancel()
    for w in workers:
        with suppress(asyncio.CancelledError):
            await w
    await app.state.ollama.aclose()
    if app.state.keycloak:
        await app.state.keycloak.aclose()
    await engine.dispose()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="FinKennis API",
        version=API_VERSION,
        description="Kennisbanken met documenten en een AI-assistent die erover antwoordt.",
        openapi_url="/api/v1/openapi.json",
        docs_url="/api/v1/docs",
        redoc_url=None,
        lifespan=lifespan,
    )
    app.state.signing_key = _signing_key
    install_handlers(app)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["API-Version", "Location"],
    )

    @app.middleware("http")
    async def api_version_header(request, call_next):
        response = await call_next(request)
        response.headers["API-Version"] = API_VERSION
        return response

    v1 = APIRouter(prefix="/api/v1")
    v1.include_router(kennisbanken.router)
    v1.include_router(documenten.router)
    v1.include_router(gesprekken.kb_router)
    v1.include_router(gesprekken.router)
    v1.include_router(gebruikers.mij_router)
    v1.include_router(gebruikers.router)

    @v1.get("/health", tags=["Beheer"])
    async def health():
        db_ok = True
        try:
            async with SessionLocal() as s:
                await s.execute(text("SELECT 1"))
        except Exception:
            db_ok = False
        ollama_ok = await app.state.ollama.health()
        return {
            "status": "ok" if db_ok and ollama_ok else "degraded",
            "database": db_ok,
            "ollama": ollama_ok,
        }

    app.include_router(v1)
    return app


app = create_app()
