import asyncio
import uuid
from collections.abc import Awaitable, Callable

from app.db.session import engine
from app.ingestion.pipeline import ingest_document, reingest_document
from app.workers.celery_app import celery_app


@celery_app.task(name="ping")
def ping() -> str:
    """Phase 0 smoke-test task; real jobs land phase-by-phase (ingest/finetune/eval/redteam)."""
    return "pong"


async def _run_and_dispose(
    coro_fn: Callable[[uuid.UUID, str], Awaitable[None]], document_id: str, file_path: str
) -> None:
    # Each Celery task call gets its own asyncio.run() (own event loop), but
    # the async engine's connection pool is a module-level singleton created
    # once at worker startup — a pooled connection from one task's loop
    # can't be reused once that loop closes (asyncpg ties connections to the
    # loop they were created on). Disposing here forces the next task to
    # open fresh connections on its own loop instead of reusing stale ones.
    try:
        await coro_fn(uuid.UUID(document_id), file_path)
    finally:
        await engine.dispose()


@celery_app.task(name="ingest_document", bind=True, max_retries=0)
def ingest_document_task(self, document_id: str, file_path: str) -> None:
    asyncio.run(_run_and_dispose(ingest_document, document_id, file_path))


@celery_app.task(name="reingest_document", bind=True, max_retries=0)
def reingest_document_task(self, document_id: str, file_path: str) -> None:
    asyncio.run(_run_and_dispose(reingest_document, document_id, file_path))
