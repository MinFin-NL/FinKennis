from app.llm.ollama import OllamaClient

# nomic-embed-text is getraind met taakprefixen; zonder prefix zakt de kwaliteit merkbaar.
DOC_PREFIX = "search_document: "
QUERY_PREFIX = "search_query: "


def _prefixes(model: str) -> tuple[str, str]:
    return (DOC_PREFIX, QUERY_PREFIX) if "nomic" in model else ("", "")


async def embed_documents(
    client: OllamaClient, teksten: list[str], batch_size: int = 32
) -> list[list[float]]:
    doc_prefix, _ = _prefixes(client.embed_model)
    vectoren: list[list[float]] = []
    for i in range(0, len(teksten), batch_size):
        batch = [doc_prefix + t for t in teksten[i : i + batch_size]]
        vectoren.extend(await client.embed(batch))
    return vectoren


async def embed_query(client: OllamaClient, vraag: str) -> list[float]:
    _, query_prefix = _prefixes(client.embed_model)
    return (await client.embed([query_prefix + vraag]))[0]
