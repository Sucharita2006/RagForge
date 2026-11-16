import math
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


def feedback_query(
    query_embedding: list[float], feedback: list[list[float]], weight: float
) -> list[float]:
    """Rocchio pseudo-relevance feedback in embedding space: move the query
    toward the (unit-length) centroid of its own top results by `weight`,
    then renormalise. No feedback or no weight leaves the query unchanged."""
    if not feedback or weight <= 0:
        return query_embedding
    centroid = [sum(column) / len(feedback) for column in zip(*feedback, strict=True)]
    centroid_norm = math.sqrt(sum(x * x for x in centroid)) or 1.0
    mixed = [q + weight * c / centroid_norm for q, c in zip(query_embedding, centroid, strict=True)]
    norm = math.sqrt(sum(x * x for x in mixed)) or 1.0
    return [x / norm for x in mixed]


def embedding_of(chunk: Chunk) -> list[float]:
    vector = chunk.embedding
    assert vector is not None, "parent chunks have no embedding and are never search results"
    return vector.to_list() if hasattr(vector, "to_list") else list(vector)
