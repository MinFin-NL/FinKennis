"""Toegang tot Ollama. Het chatmodel loopt via Pydantic AI (zie `chatmodel`); voor embeddings en de
health-check is er een dunne client voor de Ollama HTTP-API."""

import httpx
from pydantic_ai.models import Model
from pydantic_ai.models.ollama import OllamaModel
from pydantic_ai.models.openai import OpenAIChatModelSettings
from pydantic_ai.providers.ollama import OllamaProvider

from app.llm import EmbedError


def chatmodel(base_url: str, model_name: str) -> Model:
    """Het chatmodel voor de Pydantic AI-agents. Een andere aanbieder past hier in de plaats."""
    return OllamaModel(
        model_name,
        provider=OllamaProvider(base_url=f"{base_url.rstrip('/')}/v1"),
        settings=OpenAIChatModelSettings(
            temperature=0.2,
            # Qwen3 en andere 'denkende' modellen: geen redeneerstappen. Het algemene
            # `thinking=False` stuurt bij Ollama niets mee; deze instelling wel.
            openai_reasoning_effort="none",
        ),
    )


class OllamaError(EmbedError):
    pass


class OllamaClient:
    def __init__(self, base_url: str, embed_model: str):
        self.embed_model = embed_model
        self._http = httpx.AsyncClient(base_url=base_url, timeout=httpx.Timeout(300, connect=5))

    async def aclose(self) -> None:
        await self._http.aclose()

    async def embed(self, texts: list[str]) -> list[list[float]]:
        resp = await self._http.post("/api/embed", json={"model": self.embed_model, "input": texts})
        if resp.status_code != 200:
            raise OllamaError(f"Embedden mislukt ({resp.status_code}): {resp.text[:200]}")
        return resp.json()["embeddings"]

    async def health(self) -> bool:
        try:
            resp = await self._http.get("/api/tags", timeout=3)
            return resp.status_code == 200
        except httpx.HTTPError:
            return False
