"""Azure OpenAI. Chat en embeddings staan op verschillende Azure OpenAI-resources (in inno-d
de chat op die van KDAI, de embeddings op die van de invulhulp), daarom elk een eigen
endpoint en sleutel."""

import httpx
import openai
from pydantic_ai.models import Model
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.azure import AzureProvider

from app.config import Settings
from app.llm import EmbedError


def chatmodel(settings: Settings) -> Model:
    # Geen temperature: de gpt-5-chatmodellen weigeren alles behalve de standaardwaarde.
    return OpenAIChatModel(
        settings.azure_openai_deployment,
        provider=AzureProvider(
            azure_endpoint=settings.azure_openai_endpoint,
            api_version=settings.azure_openai_api_version,
            api_key=settings.azure_openai_api_key,
        ),
    )


class AzureEmbedClient:
    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None):
        self.embed_model = settings.azure_openai_embedding_deployment
        # text-embedding-3-* kan kortere vectoren teruggeven; zo past het op het bestaande
        # schema (EMBED_DIM) en blijft de HNSW-index onder de 2000 dimensies van pgvector.
        self._dim = settings.embed_dim
        self._client = openai.AsyncAzureOpenAI(
            azure_endpoint=settings.azure_openai_embedding_endpoint,
            api_version=settings.azure_openai_embedding_api_version,
            api_key=settings.azure_openai_embedding_api_key,
            timeout=120,
            http_client=httpx.AsyncClient(transport=transport) if transport else None,
        )

    async def aclose(self) -> None:
        await self._client.close()

    async def embed(self, texts: list[str]) -> list[list[float]]:
        try:
            resp = await self._client.embeddings.create(
                model=self.embed_model, input=texts, dimensions=self._dim
            )
        except openai.OpenAIError as e:
            raise EmbedError(f"Embedden mislukt: {e}") from e
        return [d.embedding for d in sorted(resp.data, key=lambda d: d.index)]

    async def health(self) -> bool:
        try:
            await self.embed(["ok"])
            return True
        except EmbedError:
            return False
