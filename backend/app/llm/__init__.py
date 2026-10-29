"""Taalmodellen. Lokaal draait alles op Ollama; in Azure op Azure OpenAI (LLM_PROVIDER)."""

from typing import Protocol

from pydantic_ai.models import Model

from app.config import Settings


class EmbedError(RuntimeError):
    pass


class EmbedClient(Protocol):
    embed_model: str

    async def embed(self, texts: list[str]) -> list[list[float]]: ...

    async def health(self) -> bool: ...

    async def aclose(self) -> None: ...


def maak_taalmodellen(settings: Settings) -> tuple[EmbedClient, Model]:
    """Geeft de embedclient en het chatmodel voor de ingestelde aanbieder."""
    if settings.llm_provider == "azure_openai":
        from app.llm import azure_openai

        return azure_openai.AzureEmbedClient(settings), azure_openai.chatmodel(settings)

    from app.llm import ollama

    return (
        ollama.OllamaClient(settings.ollama_url, settings.embed_model),
        ollama.chatmodel(settings.ollama_url, settings.chat_model),
    )
