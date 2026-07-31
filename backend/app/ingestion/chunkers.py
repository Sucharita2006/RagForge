import re

from app.providers.embeddings.base import EmbeddingProvider


def _split_into_paragraphs(text: str) -> list[str]:
    paragraphs = [p.strip() for p in text.split("\n\n")]
    return [p for p in paragraphs if p]


def _split_long_paragraph(para: str, embedder: EmbeddingProvider, chunk_size: int) -> list[str]:
    sentences = re.split(r"(?<=[.!?])\s+", para)
    pieces: list[str] = []
    current: list[str] = []
    current_tokens = 0
    for sent in sentences:
        tokens = embedder.count_tokens(sent)
        if current and current_tokens + tokens > chunk_size:
            pieces.append(" ".join(current))
            current = []
            current_tokens = 0
        current.append(sent)
        current_tokens += tokens
    if current:
        pieces.append(" ".join(current))
    return pieces


def recursive_chunk(
    text: str, embedder: EmbeddingProvider, chunk_size: int, chunk_overlap: int
) -> list[str]:
    """Greedy paragraph-packing recursive splitter (SPEC.md §3.1: recursive token
    splitter, CHUNK_SIZE/CHUNK_OVERLAP), falling back to sentence-level splitting
    for any paragraph that alone exceeds chunk_size. Token counts come from the
    embedding model's own tokenizer so chunks reliably fit its context window."""
    units: list[str] = []
    for para in _split_into_paragraphs(text):
        if embedder.count_tokens(para) <= chunk_size:
            units.append(para)
        else:
            units.extend(_split_long_paragraph(para, embedder, chunk_size))

    chunks: list[str] = []
    current: list[str] = []
    current_tokens = 0
    for unit in units:
        unit_tokens = embedder.count_tokens(unit)
        if current and current_tokens + unit_tokens > chunk_size:
            chunks.append("\n\n".join(current))
            overlap_units: list[str] = []
            overlap_tokens = 0
            for u in reversed(current):
                t = embedder.count_tokens(u)
                if overlap_tokens + t > chunk_overlap:
                    break
                overlap_units.insert(0, u)
                overlap_tokens += t
            current = overlap_units
            current_tokens = overlap_tokens
        current.append(unit)
        current_tokens += unit_tokens
    if current:
        chunks.append("\n\n".join(current))
    return chunks
