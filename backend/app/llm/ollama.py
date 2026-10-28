"""Dunne client voor de Ollama HTTP-API. De rest van de app praat alleen met deze klasse,
zodat een andere provider later achter dezelfde methoden kan."""

import json
from collections.abc import AsyncIterator

import httpx


class OllamaError(RuntimeError):
    pass


class OllamaClient:
    def __init__(self, base_url: str, chat_model: str, embed_model: str):
        self.chat_model = chat_model
        self.embed_model = embed_model
        self._http = httpx.AsyncClient(base_url=base_url, timeout=httpx.Timeout(300, connect=5))

    async def aclose(self) -> None:
        await self._http.aclose()

    async def embed(self, texts: list[str]) -> list[list[float]]:
        resp = await self._http.post("/api/embed", json={"model": self.embed_model, "input": texts})
        if resp.status_code != 200:
            raise OllamaError(f"Embedden mislukt ({resp.status_code}): {resp.text[:200]}")
        return resp.json()["embeddings"]

    async def chat_stream(self, messages: list[dict]) -> AsyncIterator[str]:
        payload = {
            "model": self.chat_model,
            "messages": messages,
            "stream": True,
            # Qwen3 en andere 'denkende' modellen: geen redeneerstappen in het antwoord.
            "think": False,
            "options": {"temperature": 0.2},
        }
        async with self._http.stream("POST", "/api/chat", json=payload) as resp:
            if resp.status_code != 200:
                body = await resp.aread()
                raise OllamaError(f"Chat mislukt ({resp.status_code}): {body[:200]!r}")
            async for line in resp.aiter_lines():
                if not line:
                    continue
                data = json.loads(line)
                if "error" in data:
                    raise OllamaError(data["error"])
                if token := data.get("message", {}).get("content"):
                    yield token
                if data.get("done"):
                    break

    async def health(self) -> bool:
        try:
            resp = await self._http.get("/api/tags", timeout=3)
            return resp.status_code == 200
        except httpx.HTTPError:
            return False
