"""Documenten omzetten naar een DoclingDocument, met structuur (kopjes, tabellen, pagina's)."""

from functools import lru_cache
from pathlib import Path

from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling_core.types.doc import DoclingDocument

# Extensie → formaat dat docling begrijpt. Platte tekst lezen we als Markdown.
ONDERSTEUNDE_EXTENSIES = {
    ".pdf",
    ".docx",
    ".pptx",
    ".xlsx",
    ".html",
    ".htm",
    ".md",
    ".markdown",
    ".txt",
    ".odt",
    ".csv",
}


class ParseError(RuntimeError):
    pass


@lru_cache
def _converter() -> DocumentConverter:
    pdf = PdfPipelineOptions()
    # Tekst-PDF's (het gros van beleidsstukken) hebben geen OCR nodig; dat scheelt veel tijd.
    pdf.do_ocr = False
    pdf.do_table_structure = True
    return DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=pdf)}
    )


def parse(path: Path, bestandsnaam: str) -> DoclingDocument:
    """CPU-zwaar: roep aan vanuit een thread."""
    ext = Path(bestandsnaam).suffix.lower()
    if ext not in ONDERSTEUNDE_EXTENSIES:
        raise ParseError(f"Bestandstype {ext or '(geen)'} wordt niet ondersteund.")

    if ext == ".txt":
        tekst = path.read_text(encoding="utf-8", errors="replace")
        return _converter().convert_string(tekst, format=InputFormat.MD, name=bestandsnaam).document

    try:
        result = _converter().convert(path, raises_on_error=True)
    except Exception as e:  # docling gooit verschillende fouttypen
        raise ParseError(f"Het document kon niet worden gelezen: {e}") from e
    return result.document
