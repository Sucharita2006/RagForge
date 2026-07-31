from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chunks import Chunk


async def dense_search(
    db: AsyncSession, query_embedding: list[float], top_k: int, ef_search: int
) -> list[tuple[Chunk, float]]:
    """Cosine similarity search via pgvector HNSW (SPEC.md §3.2 step 3).

    No metadata filters yet (Phase 1 baseline-v0) — the filtering architecture
    from implementation-plan.md §2.E1 (iterative_scan, partial indexes) only
    matters once Phase 2 adds filtered queries.
    """
    # PostgreSQL's SET does not accept bind parameters for its value (only a
    # literal token) — safe here because ef_search is guaranteed an int by
    # Settings, never raw user input.
    await db.execute(text(f"SET LOCAL hnsw.ef_search = {ef_search}"))

    distance = Chunk.embedding.cosine_distance(query_embedding)
    stmt = select(Chunk, distance.label("distance")).order_by(distance).limit(top_k)
    result = await db.execute(stmt)
    return [(chunk, 1.0 - dist) for chunk, dist in result.all()]
