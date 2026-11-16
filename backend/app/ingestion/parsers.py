import logging
import multiprocessing as mp

from pypdf import PdfReader

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


def _parse_with_docling(path: str) -> str:
    from docling.document_converter import DocumentConverter

    converter = DocumentConverter()
    result = converter.convert(path)
    return result.document.export_to_markdown()


def _parse_with_pypdf(path: str) -> str:
    reader = PdfReader(path)
    return "\n\n".join(page.extract_text() or "" for page in reader.pages)


def _docling_worker(path: str, result_queue: "mp.Queue[tuple[bool, str]]") -> None:
    try:
        result_queue.put((True, _parse_with_docling(path)))
    except Exception as e:  # noqa: BLE001 - forwarded to parent for logging
        result_queue.put((False, str(e)))


def parse_document(path: str) -> tuple[str, str]:
    """Returns (text, parser_used), with NUL characters removed.

    Some PDFs extract to text containing NUL (0x00), which Postgres cannot
    store in a text column: the whole document then failed at insert time
    (2 of the golden set's 37 papers did, on a fresh seed)."""
    text, parser_used = _extract(path)
    return text.replace("\x00", ""), parser_used


def _extract(path: str) -> tuple[str, str]:
    """Docling primary, pypdf fallback (SPEC.md §3.1).

    Docling's automatic OCR fallback (RapidOCR) has no internal timeout and
    can run effectively unbounded on an image-heavy scanned PDF on CPU —
    observed hanging for hours on one real corpus document. Runs in a real
    child *process* (not a thread) so it can be forcibly killed on timeout:
    an earlier thread-based version fell back to pypdf correctly but left
    the abandoned OCR work running at ~900% CPU indefinitely afterward,
    since Python cannot kill a thread — observed live, mid-corpus, on a
    restarted worker. A process can be SIGKILLed and its CPU actually
    reclaimed by the OS.
    """
    # "spawn", not Linux's default "fork": with TORCH_DEVICE=cuda the worker
    # has already initialised CUDA for the embedder, and a forked child
    # cannot use CUDA, so Docling failed on every document and fell back to
    # pypdf. A spawned child starts clean and initialises its own.
    ctx = mp.get_context("spawn")
    result_queue: mp.Queue = ctx.Queue()
    process = ctx.Process(target=_docling_worker, args=(path, result_queue), daemon=True)
    process.start()
    process.join(timeout=settings.DOCLING_TIMEOUT_SECONDS)

    if process.is_alive():
        logger.warning(
            "Docling parse exceeded %ds for %s (likely heavy OCR), killing worker process "
            "and falling back to pypdf",
            settings.DOCLING_TIMEOUT_SECONDS,
            path,
        )
        process.kill()
        process.join()
        return _parse_with_pypdf(path), "pypdf"

    if not result_queue.empty():
        ok, payload = result_queue.get()
        if ok and payload.strip():
            return payload, "docling"
        logger.warning(
            "Docling %s for %s, falling back to pypdf",
            "returned empty text" if ok else f"failed ({payload})",
            path,
        )
    else:
        logger.warning("Docling worker exited without a result for %s, falling back to pypdf", path)

    return _parse_with_pypdf(path), "pypdf"
