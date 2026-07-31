import logging

from pypdf import PdfReader

logger = logging.getLogger(__name__)


def _parse_with_docling(path: str) -> str:
    from docling.document_converter import DocumentConverter

    converter = DocumentConverter()
    result = converter.convert(path)
    return result.document.export_to_markdown()


def _parse_with_pypdf(path: str) -> str:
    reader = PdfReader(path)
    return "\n\n".join(page.extract_text() or "" for page in reader.pages)


def parse_document(path: str) -> tuple[str, str]:
    """Returns (text, parser_used). Docling primary, pypdf fallback (SPEC.md §3.1)."""
    try:
        text = _parse_with_docling(path)
        if text.strip():
            return text, "docling"
        logger.warning("Docling returned empty text for %s, falling back to pypdf", path)
    except Exception:
        logger.warning("Docling parse failed for %s, falling back to pypdf", path, exc_info=True)
    return _parse_with_pypdf(path), "pypdf"
