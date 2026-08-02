import json
import logging
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.evals.bootstrap import bootstrap_ci
from app.evals.judge import JudgeProvider
from app.evals.retrieval_metrics import (
    abstention_correct,
    hit_rate,
    ndcg_at_k,
    reciprocal_rank,
    violates_forbidden_strings,
)
from app.evals.schemas import GoldenItem
from app.generation.generator import generate_answer
from app.models.documents import Document
from app.models.evals import EvalResult, EvalRun
from app.providers.embeddings.base import EmbeddingProvider
from app.providers.llm.base import LLMProvider
from app.retrieval.assembly import assemble_context, expand_to_parents
from app.retrieval.pipeline import retrieve as run_retrieval_pipeline

settings = get_settings()
logger = logging.getLogger(__name__)

_JUDGED_METRIC_FIELDS = (
    "faithfulness",
    "answer_correctness",
    "context_precision",
    "context_recall",
)


def load_golden_set(path: Path) -> list[GoldenItem]:
    return [
        GoldenItem(**json.loads(line)) for line in path.read_text().splitlines() if line.strip()
    ]


async def _external_ids_for(db: AsyncSession, document_ids: list[uuid.UUID]) -> dict[str, str]:
    if not document_ids:
        return {}
    result = await db.execute(
        select(Document.id, Document.external_id).where(Document.id.in_(document_ids))
    )
    return {str(doc_id): ext_id for doc_id, ext_id in result.all() if ext_id}


async def run_item(
    db: AsyncSession,
    item: GoldenItem,
    embedder: EmbeddingProvider,
    llm: LLMProvider,
    judge: JudgeProvider,
    full_pipeline: bool,
) -> dict:
    """Retrieval for every item; generation + judge scoring only when
    `full_pipeline` (generation is the expensive step on CPU - the runner
    decides per-item which items get it, see execute_eval_run)."""
    start = time.monotonic()
    query_embedding = embedder.embed_query(item.question)
    fused = await run_retrieval_pipeline(db, item.question, query_embedding)
    top_chunks = fused[: settings.FINAL_TOP_K]

    document_ids = list({c.chunk.document_id for c in top_chunks})
    external_id_by_doc = await _external_ids_for(db, document_ids)
    ranked_external_ids = [
        external_id_by_doc[str(c.chunk.document_id)]
        for c in top_chunks
        if str(c.chunk.document_id) in external_id_by_doc
    ]

    metrics: dict = {}
    if item.expected_arxiv_ids:
        metrics["hit_rate"] = hit_rate(ranked_external_ids, item.expected_arxiv_ids)
        metrics["reciprocal_rank"] = reciprocal_rank(ranked_external_ids, item.expected_arxiv_ids)
        metrics["ndcg@10"] = ndcg_at_k(ranked_external_ids, item.expected_arxiv_ids, 10)

    retrieved_payload = {
        "candidates": [
            {
                "chunk_id": str(c.chunk.id),
                "document_external_id": external_id_by_doc.get(str(c.chunk.document_id)),
                "rerank_score": c.rerank_score,
            }
            for c in top_chunks
        ]
    }

    answer_payload: dict = {}
    judge_notes: str | None = None

    if full_pipeline:
        expanded = await expand_to_parents(db, [c.chunk for c in top_chunks])
        context, used_chunks = assemble_context(expanded, settings.MAX_CONTEXT_TOKENS)
        valid_chunk_ids = {str(c.id) for c in used_chunks}
        answer, raw = await generate_answer(llm, item.question, context, valid_chunk_ids)
        answer_text = " ".join(c.text for c in answer.answer_sentences)

        answer_payload = {
            "text": answer_text,
            "insufficient_context": answer.insufficient_context,
            "model": llm.model_name,
            "latency_ms": raw["latency_ms"],
            "claims": [c.model_dump() for c in answer.answer_sentences],
        }
        metrics["abstained"] = answer.insufficient_context
        metrics["abstention_correct"] = abstention_correct(
            answer.insufficient_context, item.unanswerable
        )

        if item.forbidden_strings:
            metrics["adversarial_safe"] = not violates_forbidden_strings(
                answer_text, item.forbidden_strings
            )
        elif not item.unanswerable and not answer.insufficient_context:
            judge_scores = await judge.score(
                item.id, item.question, context, answer_text, item.reference_answer
            )
            judge_notes = judge_scores.get("rationale")
            for field in _JUDGED_METRIC_FIELDS:
                if judge_scores.get(field) is not None:
                    metrics[field] = judge_scores[field]

    metrics["latency_ms"] = int((time.monotonic() - start) * 1000)
    return {
        "metrics": metrics,
        "retrieved": retrieved_payload,
        "answer": answer_payload,
        "judge_notes": judge_notes,
    }


def aggregate_metrics(results: list[EvalResult], items_by_id: dict[str, GoldenItem]) -> dict:
    """Bootstrap CI per metric over every item where it was computed, plus
    the two named subset metrics SPEC.md §7.2 gates on separately."""
    per_metric: dict[str, list[float]] = {}
    unanswerable_abstained: list[float] = []
    answered_correctly: list[float] = []  # 1.0 if answered-and-answerable, for answered-precision

    for result in results:
        for key, value in result.metrics.items():
            if isinstance(value, bool):
                per_metric.setdefault(key, []).append(1.0 if value else 0.0)
            elif isinstance(value, int | float):
                per_metric.setdefault(key, []).append(float(value))

        item = items_by_id.get(result.question_id)
        if item is None or "abstained" not in result.metrics:
            continue
        abstained = bool(result.metrics["abstained"])
        if item.unanswerable:
            unanswerable_abstained.append(1.0 if abstained else 0.0)
        if not abstained:
            # among items the system chose to answer, was it actually
            # answerable? (answered-precision, SPEC.md §7.2)
            answered_correctly.append(0.0 if item.unanswerable else 1.0)

    aggregate = {key: bootstrap_ci(values) for key, values in per_metric.items()}
    if unanswerable_abstained:
        aggregate["abstention_recall_unanswerable"] = bootstrap_ci(unanswerable_abstained)
    if answered_correctly:
        aggregate["answered_precision"] = bootstrap_ci(answered_correctly)
    return aggregate


async def execute_eval_run(
    db: AsyncSession,
    run_id: uuid.UUID,
    dataset_path: Path,
    embedder: EmbeddingProvider,
    llm: LLMProvider,
    full_pipeline_ids: set[str] | None = None,
) -> None:
    """`full_pipeline_ids=None` runs generation+judge on every item;
    otherwise only on that subset (retrieval-only metrics still run for
    all items) - see DECISIONS.md 2026-08-01 on why a full 120-item
    generation+judge pass isn't run by default on this hardware."""
    run = await db.get(EvalRun, run_id)
    assert run is not None
    judge = JudgeProvider(llm)

    items = load_golden_set(dataset_path)
    items_by_id = {item.id: item for item in items}
    results: list[EvalResult] = []
    failures: list[str] = []

    # Per-item isolation: one slow/failing item (a real ReadTimeout on a
    # large multi-hop context killed an entire run before this fix - see
    # DECISIONS.md 2026-08-02) must not discard every item that already
    # succeeded and was committed. Only a run-level problem (DB down, bad
    # dataset path) should abort the whole run; that still propagates since
    # nothing here catches it before load_golden_set/db.get above.
    for item in items:
        try:
            full = full_pipeline_ids is None or item.id in full_pipeline_ids
            outcome = await run_item(db, item, embedder, llm, judge, full)
            eval_result = EvalResult(
                run_id=run_id,
                question_id=item.id,
                question_type=item.type,
                metrics=outcome["metrics"],
                retrieved=outcome["retrieved"],
                answer=outcome["answer"],
                judge_notes=outcome["judge_notes"],
            )
            db.add(eval_result)
            await db.commit()
            results.append(eval_result)
        except Exception:
            logger.exception("eval item %s failed", item.id)
            await db.rollback()
            failures.append(item.id)

    # a per-item rollback above expires every loaded object in the session
    # (independent of async_session_maker's expire_on_commit=False, which
    # only governs the commit path) - re-fetch explicitly rather than rely
    # on implicit lazy-refresh of a stale reference.
    run = await db.get(EvalRun, run_id)
    assert run is not None
    run.metrics = aggregate_metrics(results, items_by_id)
    run.status = "completed" if results else "failed"
    if failures:
        run.error = f"{len(failures)}/{len(items)} items failed: {failures}"
    run.finished_at = datetime.now(UTC)
    await db.commit()
