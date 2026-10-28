"""Structuurbewust chunken: kopjes blijven bij hun tekst, tabellen worden niet doormidden gehakt."""

import re
from dataclasses import dataclass, field

from docling_core.transforms.chunker.hybrid_chunker import HybridChunker
from docling_core.transforms.chunker.tokenizer.base import BaseTokenizer
from docling_core.types.doc import DoclingDocument

_TOKEN_RE = re.compile(r"\w+|[^\w\s]", re.UNICODE)


class BenaderdeTokenizer(BaseTokenizer):
    """Telt woorden en leestekens, keer 1,3 voor subwoorden in het Nederlands.

    Een exacte tokenizer zou een HuggingFace-model moeten downloaden. Voor het afkappen van
    chunks is een benadering genoeg, en nomic-embed-text kan ruim 2k tokens aan.
    """

    max_tokens: int = 512

    def count_tokens(self, text: str) -> int:
        return int(len(_TOKEN_RE.findall(text)) * 1.3)

    def get_max_tokens(self) -> int:
        return self.max_tokens

    def get_tokenizer(self):
        # semchunk splitst te lange tekst en verwacht hier een functie die tokens telt.
        return self.count_tokens


@dataclass
class TekstChunk:
    tekst: str  # wat de gebruiker en het taalmodel te zien krijgen
    context_tekst: str  # tekst met kopjes ervoor; dit wordt ge-embed
    kopjes: list[str] = field(default_factory=list)
    pagina: int | None = None


def chunk_document(doc: DoclingDocument, max_tokens: int = 512) -> list[TekstChunk]:
    chunker = HybridChunker(tokenizer=BenaderdeTokenizer(max_tokens=max_tokens), merge_peers=True)
    chunks: list[TekstChunk] = []
    for c in chunker.chunk(dl_doc=doc):
        tekst = c.text.strip()
        if not tekst:
            continue
        pagina = next(
            (prov.page_no for item in c.meta.doc_items for prov in (item.prov or [])),
            None,
        )
        chunks.append(
            TekstChunk(
                tekst=tekst,
                context_tekst=chunker.contextualize(chunk=c),
                kopjes=list(c.meta.headings or []),
                pagina=pagina,
            )
        )
    return chunks
