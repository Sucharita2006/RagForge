from app.models.chunks import Chunk


def assemble_context(chunks: list[Chunk], max_context_tokens: int) -> tuple[str, list[Chunk]]:
    """Phase 1: greedy pack by descending similarity up to MAX_CONTEXT_TOKENS.

    No parent-chunk expansion or lost-in-the-middle reorder yet (Phase 2) —
    with DENSE_TOP_K=50 candidates vastly exceeding the token budget, this
    still naturally caps the effective chunk count each query uses.
    """
    used: list[Chunk] = []
    total_tokens = 0
    for chunk in chunks:
        if total_tokens + chunk.token_count > max_context_tokens:
            break
        used.append(chunk)
        total_tokens += chunk.token_count

    context = "\n\n".join(f"[chunk_id={chunk.id}]\n{chunk.content}" for chunk in used)
    return context, used
