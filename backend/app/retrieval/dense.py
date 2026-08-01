import uuid

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.chunks import Chunk

settings = get_settings()


async def dense_search(
    db: AsyncSession,
    query_embedding: list[float],
    top_k: int,
    ef_search: int,
    document_id: uuid.UUID | None = None,
) -> list[tuple[Chunk, float]]:
    """Cosine similarity search via pgvector HNSW (SPEC.md §3.2 step 3).

    Parent chunks are never search candidates (SPEC.md §3.2 step 7 — only
    children are embedded). An optional document_id filter exercises the
    filtering architecture (implementation-plan.md §2.E1): pgvector has no
    cost-based pre/post-filter planner, so `hnsw.iterative_scan` is set as a
    session default to avoid the documented "selective filter silently
    returns fewer than k rows" failure mode of the naive post-filter default.
    """
    # PostgreSQL's SET does not accept bind parameters for its value (only a
    # literal token) — safe here because these are guaranteed by Settings,
    # never raw user input.
    await db.execute(text(f"SET LOCAL hnsw.ef_search = {ef_search}"))
    await db.execute(text(f"SET LOCAL hnsw.iterative_scan = {settings.HNSW_ITERATIVE_SCAN}"))
    await db.execute(text(f"SET LOCAL hnsw.max_scan_tuples = {settings.HNSW_MAX_SCAN_TUPLES}"))

    distance = Chunk.embedding.cosine_distance(query_embedding)
    stmt = select(Chunk, distance.label("distance")).where(Chunk.is_parent.is_(False))
    if document_id is not None:
        stmt = stmt.where(Chunk.document_id == document_id)
    stmt = stmt.order_by(distance).limit(top_k)

    result = await db.execute(stmt)
    return [(chunk, 1.0 - dist) for chunk, dist in result.all()]
