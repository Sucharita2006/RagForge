import asyncio
import uuid
from collections.abc import Awaitable, Callable
from pathlib import Path

from app.db.session import async_session_maker, engine
from app.evals.runner import execute_eval_run
from app.ingestion.pipeline import ingest_document, reingest_document
from app.providers.embeddings.bge_small import get_embedding_provider
from app.providers.llm.base import LLMProvider
from app.providers.llm.gemini import GeminiProvider
from app.providers.llm.ollama import OllamaProvider
from app.providers.llm.openrouter import OpenRouterProvider
from app.workers.celery_app import celery_app


def _build_eval_llm(llm_provider: str) -> LLMProvider:
    """`llm_provider` lets one eval run swap generation onto a hosted model
    (free-tier Gemini or OpenRouter) instead of self-hosted Ollama - not a
    production /query change, just an option for eval runs where local CPU
    memory/time is the constraint (DECISIONS.md 2026-08-03, 2026-08-06)."""
    if llm_provider == "gemini":
        return GeminiProvider()
    if llm_provider == "openrouter":
        return OpenRouterProvider()
    if llm_provider == "ollama":
        # eval runs are background/non-interactive - a much longer per-call
        # budget than the live-query default absorbs slow multi-hop-context
        # generations instead of ReadTimeout-ing (DECISIONS.md 2026-08-02;
        # per-item failures are also now isolated in execute_eval_run regardless).
        return OllamaProvider(timeout=1200.0)
    raise ValueError(f"unknown llm_provider: {llm_provider!r}")


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


async def _run_eval_and_dispose(
    run_id: str, dataset_path: str, full_pipeline_ids: list[str] | None, llm_provider: str
) -> None:
    try:
        async with async_session_maker() as db:
            embedder = get_embedding_provider()
            llm = _build_eval_llm(llm_provider)
            await execute_eval_run(
                db,
                uuid.UUID(run_id),
                Path(dataset_path),
                embedder,
                llm,
                set(full_pipeline_ids) if full_pipeline_ids is not None else None,
            )
    finally:
        await engine.dispose()


@celery_app.task(name="run_eval", bind=True, max_retries=0)
def run_eval_task(
    self,
    run_id: str,
    dataset_path: str,
    full_pipeline_ids: list[str] | None = None,
    llm_provider: str = "ollama",
) -> None:
    asyncio.run(_run_eval_and_dispose(run_id, dataset_path, full_pipeline_ids, llm_provider))
