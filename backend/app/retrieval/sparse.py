import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chunks import Chunk


async def sparse_search(
    db: AsyncSession, query_text: str, top_k: int, document_id: uuid.UUID | None = None
) -> list[tuple[Chunk, float]]:
    """Postgres full-text search (SPEC.md §3.2 step 4): websearch_to_tsquery +
    ts_rank_cd over the tsv generated column. Parent chunks are never search
    candidates (only children are embedded/searched — SPEC.md §3.2 step 7)."""
    tsquery = func.websearch_to_tsquery("english", query_text)
    rank = func.ts_rank_cd(Chunk.tsv, tsquery).label("rank")
    stmt = select(Chunk, rank).where(Chunk.is_parent.is_(False)).where(Chunk.tsv.op("@@")(tsquery))
    if document_id is not None:
        stmt = stmt.where(Chunk.document_id == document_id)
    stmt = stmt.order_by(rank.desc()).limit(top_k)

    result = await db.execute(stmt)
    return [(chunk, float(r)) for chunk, r in result.all()]
