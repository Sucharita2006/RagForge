from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.learning import ModelRegistry

_RERANKER_KIND = "reranker"


async def active_reranker_path(db: AsyncSession) -> str:
    """Resolve which reranker the pipeline should load right now.

    Read from the DB on each retrieval rather than cached in-process,
    deliberately: promotion happens in the API process but the Celery worker
    runs the same pipeline in a *different* process, so an in-memory pointer
    would leave the worker serving a stale model until restart - the exact
    "which model actually answered this?" ambiguity the registry exists to
    remove. The cost is one indexed SELECT against a table with a handful of
    rows, against a rerank step measured at ~6.5s (Phase 5 waterfall), so
    it's not a latency consideration.

    The *model* itself is still loaded once per distinct path via
    `get_reranker_provider`'s lru_cache - it's only the pointer that's re-read.
    """
    result = await db.execute(
        select(ModelRegistry).where(
            ModelRegistry.kind == _RERANKER_KIND, ModelRegistry.status == "active"
        )
    )
    active = result.scalars().first()
    if active is None:
        # Falling back to config keeps retrieval working if the registry is
        # empty (fresh DB, or a failed migration) rather than 500-ing the
        # whole query path over a bookkeeping table.
        return get_settings().RERANKER_MODEL
    return active.artifact_path or active.base_model
