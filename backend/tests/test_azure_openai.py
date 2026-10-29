import json

import httpx

from app.config import Settings
from app.llm import EmbedError
from app.llm.azure_openai import AzureEmbedClient


def _settings() -> Settings:
    return Settings(
        azure_openai_embedding_endpoint="https://aoai.example.org/",
        azure_openai_embedding_api_key="sleutel",
        embed_dim=768,
    )


async def test_embed_vraagt_korte_vectoren_en_houdt_de_volgorde_aan():
    verzoeken: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        verzoeken.append(json.loads(request.content))
        # Azure mag de volgorde husselen; index bepaalt welke vector bij welke tekst hoort.
        data = [
            {"object": "embedding", "index": 1, "embedding": [0.0, 1.0]},
            {"object": "embedding", "index": 0, "embedding": [1.0, 0.0]},
        ]
        return httpx.Response(
            200,
            json={
                "object": "list",
                "data": data,
                "model": "text-embedding-3-large",
                "usage": {"prompt_tokens": 2, "total_tokens": 2},
            },
        )

    client = AzureEmbedClient(_settings(), transport=httpx.MockTransport(handler))
    vectoren = await client.embed(["a", "b"])
    await client.aclose()

    assert vectoren == [[1.0, 0.0], [0.0, 1.0]]
    assert verzoeken[0]["dimensions"] == 768
    assert verzoeken[0]["model"] == "text-embedding-3-large"


async def test_fout_van_azure_wordt_embederror():
    client = AzureEmbedClient(
        _settings(),
        transport=httpx.MockTransport(lambda r: httpx.Response(400, json={"error": {}})),
    )
    try:
        await client.embed(["a"])
        raise AssertionError("verwachtte EmbedError")
    except EmbedError:
        pass
    finally:
        await client.aclose()
    assert (
        await AzureEmbedClient(
            _settings(), transport=httpx.MockTransport(lambda r: httpx.Response(500))
        ).health()
        is False
    )
