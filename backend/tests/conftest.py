"""Tests draaien tegen een echte Postgres (met pgvector), in een aparte database finkennis_test.
Ollama wordt vervangen door een nepclient, zodat er geen model nodig is."""

import os

os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://finkennis:finkennis@localhost:5433/finkennis_test"
)
os.environ["INGEST_WORKER_ENABLED"] = "false"
os.environ["AUTH_MODE"] = "none"

import asyncio  # noqa: E402
import hashlib  # noqa: E402

import asyncpg  # noqa: E402
import pytest  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.config import get_settings  # noqa: E402


class FakeOllama:
    """Deterministische 'embeddings' op basis van woorden, zodat zoeken voorspelbaar is."""

    chat_model = "nep"
    embed_model = "nep-embed"

    def __init__(self):
        self.laatste_berichten: list[dict] | None = None

    async def embed(self, texts: list[str]) -> list[list[float]]:
        dim = get_settings().embed_dim
        vectoren = []
        for t in texts:
            v = [0.0] * dim
            for woord in t.lower().split():
                v[int(hashlib.md5(woord.encode()).hexdigest(), 16) % dim] += 1.0
            if not any(v):
                v[0] = 1.0
            vectoren.append(v)
        return vectoren

    async def chat_stream(self, messages: list[dict]):
        self.laatste_berichten = messages
        for token in ["Het ", "antwoord ", "staat ", "in ", "[1]."]:
            await asyncio.sleep(0)
            yield token

    async def health(self) -> bool:
        return True

    async def aclose(self) -> None:
        pass


async def _maak_testdatabase(url: str) -> None:
    dsn = url.replace("+asyncpg", "")
    naam = dsn.rsplit("/", 1)[1]
    admin = await asyncpg.connect(dsn.rsplit("/", 1)[0] + "/postgres")
    try:
        if not await admin.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", naam):
            await admin.execute(f'CREATE DATABASE "{naam}"')
    finally:
        await admin.close()


@pytest.fixture(scope="session", autouse=True)
async def database():
    from alembic.config import Config

    from alembic import command

    await _maak_testdatabase(get_settings().database_url)
    cfg = Config("alembic.ini")
    await asyncio.to_thread(command.upgrade, cfg, "head")
    yield


@pytest.fixture(autouse=True)
async def schone_tabellen(database):
    from app.db import engine

    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE kennisbank CASCADE"))
    yield


@pytest.fixture
def fake_ollama() -> FakeOllama:
    return FakeOllama()


@pytest.fixture
async def app(fake_ollama, tmp_path):
    from app.main import app as fastapi_app

    settings = get_settings()
    settings.upload_dir = tmp_path / "uploads"
    fastapi_app.state.ollama = fake_ollama
    yield fastapi_app
    fastapi_app.dependency_overrides.clear()


@pytest.fixture
async def client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
