from docling.datamodel.base_models import InputFormat

from app.rag.chunking import BenaderdeTokenizer, chunk_document
from app.rag.parsing import _converter

MARKDOWN = """# Reiskostenregeling

## Woon-werkverkeer

Medewerkers krijgen een vergoeding van 0,23 euro per kilometer voor woon-werkverkeer.

## Dienstreizen

Voor dienstreizen geldt een vergoeding van de werkelijke kosten van het openbaar vervoer.
"""


def test_kopjes_blijven_bij_hun_tekst():
    doc = _converter().convert_string(MARKDOWN, format=InputFormat.MD, name="regeling.md").document
    chunks = chunk_document(doc, max_tokens=512)

    woon_werk = next(c for c in chunks if "0,23 euro" in c.tekst)
    assert "Woon-werkverkeer" in woon_werk.kopjes
    # De kopjes gaan mee in de tekst die ge-embed wordt, niet in de getoonde tekst.
    assert "Woon-werkverkeer" in woon_werk.context_tekst


def test_lange_tekst_wordt_gesplitst():
    alinea = " ".join(["woord"] * 400)
    md = "# Titel\n\n" + "\n\n".join([alinea] * 5)
    doc = _converter().convert_string(md, format=InputFormat.MD, name="lang.md").document
    tokenizer = BenaderdeTokenizer(max_tokens=200)
    chunks = chunk_document(doc, max_tokens=200)

    assert len(chunks) > 5
    assert all(tokenizer.count_tokens(c.context_tekst) <= 200 for c in chunks)
