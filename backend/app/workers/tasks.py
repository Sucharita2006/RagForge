import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path

from opentelemetry import trace

from app.config import get_settings
from app.db.session import async_session_maker, engine
from app.evals.runner import execute_eval_run
from app.ingestion.pipeline import ingest_document, reingest_document
from app.learning.clustering import cluster_recent_failures
from app.learning.finetune import (
    ARTIFACT_ROOT,
    load_training_examples,
    register_candidate,
    train_reranker,
)
from app.observability.monitor import (
    check_faithfulness_drop,
    sample_recent_answers,
    score_sample_faithfulness,
)
from app.providers.embeddings.bge_small import get_embedding_provider
from app.providers.llm.base import LLMProvider
from app.providers.llm.gemini import GeminiProvider
from app.providers.llm.ollama import OllamaProvider
from app.providers.llm.openrouter import OpenRouterProvider
from app.retrieval.rerankers.registry import active_reranker_path
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


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
    run_id: str,
    dataset_path: str,
    full_pipeline_ids: list[str] | None,
    llm_provider: str,
    reranker_path: str | None,
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
                reranker_path,
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
    reranker_path: str | None = None,
) -> None:
    asyncio.run(
        _run_eval_and_dispose(run_id, dataset_path, full_pipeline_ids, llm_provider, reranker_path)
    )


async def _run_online_monitor(llm_provider: str) -> None:
    """SPEC.md §3.8's nightly online monitor: judge-score a sample of real
    production answers for faithfulness, emit the result as an EVALUATOR
    span so it lands in the same time series the Traces/Analytics pages
    read, and log an alert if it dropped vs the prior 7-day window."""
    tracer = trace.get_tracer(__name__)
    settings = get_settings()
    try:
        async with async_session_maker() as db:
            sample = await sample_recent_answers(db, settings.ONLINE_MONITOR_SAMPLE_SIZE)
            if not sample:
                logger.info("online monitor: no recent non-abstained answers to score")
                return

            llm = _build_eval_llm(llm_provider)
            scores = await score_sample_faithfulness(db, llm, sample)
            if not scores:
                logger.warning("online monitor: sampled %d answers, none scorable", len(sample))
                return

            mean_faithfulness = sum(scores) / len(scores)
            alert = await check_faithfulness_drop(db, mean_faithfulness)

        with tracer.start_as_current_span(
            "online_monitor",
            attributes={
                "openinference.span.kind": "EVALUATOR",
                "monitor.mean_faithfulness": mean_faithfulness,
                "monitor.sample_size": len(scores),
                "monitor.sampled_answers": len(sample),
            },
        ) as span:
            if alert:
                span.set_attribute("monitor.alert", alert)
                logger.warning("online monitor ALERT: %s", alert)
        logger.info(
            "online monitor: mean faithfulness %.3f over %d scored answers",
            mean_faithfulness,
            len(scores),
        )
    finally:
        await engine.dispose()


@celery_app.task(name="run_online_monitor", bind=True, max_retries=0)
def run_online_monitor_task(self, llm_provider: str = "ollama") -> None:
    asyncio.run(_run_online_monitor(llm_provider))


async def _finetune_reranker(max_pairs: int | None, epochs: int, batch_size: int) -> None:
    """Train a candidate reranker from mined pairs and register it (SPEC.md
    §3.5). Registered as `candidate` only - promotion requires winning a
    measured A/B, which this task deliberately does not do for itself."""
    settings = get_settings()
    try:
        async with async_session_maker() as db:
            examples = await load_training_examples(db, max_pairs)
            if not examples:
                logger.warning("reranker fine-tune: no training pairs available, nothing to do")
                return

            active_base = await active_reranker_path(db)
            output_dir = ARTIFACT_ROOT / f"reranker-{datetime.now(UTC):%Y%m%d-%H%M%S}"

        # Training is CPU-bound and synchronous; run it outside the session so
        # a multi-minute fit doesn't hold a DB connection open the whole time.
        train_config = await asyncio.to_thread(
            train_reranker,
            examples,
            settings.RERANKER_MODEL,
            output_dir,
            epochs,
            batch_size,
        )
        train_config["trained_against_active"] = active_base

        async with async_session_maker() as db:
            candidate = await register_candidate(
                db, "reranker", settings.RERANKER_MODEL, str(output_dir), train_config
            )
        logger.info(
            "reranker fine-tune complete: candidate %s from %d examples in %.1fs",
            candidate.id,
            train_config["n_examples"],
            train_config["train_seconds"],
        )
    finally:
        await engine.dispose()


@celery_app.task(name="finetune_reranker", bind=True, max_retries=0)
def finetune_reranker_task(
    self, max_pairs: int | None = None, epochs: int = 1, batch_size: int = 32
) -> None:
    asyncio.run(_finetune_reranker(max_pairs, epochs, batch_size))


async def _cluster_failures(window_hours: int) -> None:
    try:
        async with async_session_maker() as db:
            clusters = await cluster_recent_failures(db, window_hours)
        logger.info("failure clustering: wrote %d clusters", len(clusters))
    finally:
        await engine.dispose()


@celery_app.task(name="cluster_failures", bind=True, max_retries=0)
def cluster_failures_task(self, window_hours: int = 168) -> None:
    asyncio.run(_cluster_failures(window_hours))
