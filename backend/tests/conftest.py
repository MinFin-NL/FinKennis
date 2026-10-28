"""Tests draaien tegen een echte Postgres (met pgvector), in een aparte database finkennis_test.
Ollama wordt vervangen door een nepclient en het chatmodel door een Pydantic AI-FunctionModel,
zodat er geen model nodig is."""

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
from pydantic_ai.messages import (  # noqa: E402
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    UserPromptPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.config import get_settings  # noqa: E402


class FakeOllama:
    """Deterministische 'embeddings' op basis van woorden, zodat zoeken voorspelbaar is."""

    embed_model = "nep-embed"

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

    async def health(self) -> bool:
        return True

    async def aclose(self) -> None:
        pass


def _als_tekst(messages: list[ModelMessage]) -> list[dict]:
    """Berichten als {role, content}, zodat tests er makkelijk op kunnen controleren."""
    uit = []
    for m in messages:
        if isinstance(m, ModelRequest) and m.instructions:
            uit.append({"role": "system", "content": m.instructions})
        for p in m.parts:
            if isinstance(p, UserPromptPart):
                uit.append({"role": "user", "content": p.content})
            elif isinstance(p, TextPart):
                uit.append({"role": "assistant", "content": p.content})
    return uit


class FakeChat:
    """Neemt op wat de agents naar het model sturen. Het herschrijven loopt zonder streaming,
    het antwoord met."""

    def __init__(self):
        self.laatste_berichten: list[dict] | None = None
        self.herschrijfberichten: list[dict] | None = None
        self.herschreven = ""
        self.model = FunctionModel(self._herschrijf, stream_function=self._antwoord)

    def _herschrijf(self, messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        self.herschrijfberichten = _als_tekst(messages)
        return ModelResponse(parts=[TextPart(self.herschreven)])

    async def _antwoord(self, messages: list[ModelMessage], info: AgentInfo):
        self.laatste_berichten = _als_tekst(messages)
        for token in ["Het ", "antwoord ", "staat ", "in ", "[1]."]:
            yield token


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
def fake_chat() -> FakeChat:
    return FakeChat()


@pytest.fixture
async def app(fake_ollama, fake_chat, tmp_path):
    from app.main import app as fastapi_app

    settings = get_settings()
    settings.upload_dir = tmp_path / "uploads"
    fastapi_app.state.ollama = fake_ollama
    fastapi_app.state.chatmodel = fake_chat.model
    yield fastapi_app
    fastapi_app.dependency_overrides.clear()


@pytest.fixture
async def client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
