import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chunks import Chunk


async def expand_to_parents(db: AsyncSession, chunks: list[Chunk]) -> list[Chunk]:
    """Replace child chunks with their parent chunk, deduping overlapping
    parents (SPEC.md §3.2 step 7). Chunks with no parent_id (e.g. a document
    too short to need parent-child splitting) pass through unchanged.
    `chunks` must already be rank-ordered; the returned list preserves that
    order (first occurrence of a parent wins its position)."""
    parent_ids = {c.parent_id for c in chunks if c.parent_id is not None}
    parents_by_id: dict[uuid.UUID, Chunk] = {}
    if parent_ids:
        result = await db.execute(select(Chunk).where(Chunk.id.in_(parent_ids)))
        parents_by_id = {p.id: p for p in result.scalars().all()}

    expanded: list[Chunk] = []
    seen_parent_ids: set[uuid.UUID] = set()
    for chunk in chunks:
        if chunk.parent_id is not None and chunk.parent_id in parents_by_id:
            if chunk.parent_id in seen_parent_ids:
                continue  # another, higher-ranked child already expanded this parent in
            seen_parent_ids.add(chunk.parent_id)
            expanded.append(parents_by_id[chunk.parent_id])
        else:
            expanded.append(chunk)
    return expanded


def reorder_lost_in_the_middle(chunks: list[Chunk]) -> list[Chunk]:
    """Alternately place chunks at the start and end of the sequence so the
    highest-scored ones sit at the beginning *and* end of the context, and
    the lowest-scored end up buried in the middle — the position attention
    tends to weight least (SPEC.md §3.2 step 7). `chunks` must already be
    rank-ordered (best first)."""
    reordered: list[Chunk | None] = [None] * len(chunks)
    left, right = 0, len(chunks) - 1
    for i, chunk in enumerate(chunks):
        if i % 2 == 0:
            reordered[left] = chunk
            left += 1
        else:
            reordered[right] = chunk
            right -= 1
    return [c for c in reordered if c is not None]


def assemble_context(chunks: list[Chunk], max_context_tokens: int) -> tuple[str, list[Chunk]]:
    """Greedy pack by descending relevance up to MAX_CONTEXT_TOKENS, then
    reorder for lost-in-the-middle mitigation before formatting.

    `used` (the second return value) stays in original rank order — it's
    used for citation-hygiene checks (implementation-plan.md), where order
    doesn't matter — while the formatted `context` string uses the
    lost-in-the-middle reordering.
    """
    used: list[Chunk] = []
    total_tokens = 0
    for chunk in chunks:
        if total_tokens + chunk.token_count > max_context_tokens:
            break
        used.append(chunk)
        total_tokens += chunk.token_count

    reordered = reorder_lost_in_the_middle(used)
    context = "\n\n".join(f"[chunk_id={chunk.id}]\n{chunk.content}" for chunk in reordered)
    return context, used
