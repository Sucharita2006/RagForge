import logging
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.evals.judge import JudgeProvider
from app.models.answers import Answer
from app.models.chunks import Chunk
from app.models.queries import Query
from app.models.spans import Span
from app.providers.llm.base import LLMProvider

logger = logging.getLogger(__name__)

_MONITOR_SPAN_KIND = "EVALUATOR"
_MONITOR_SPAN_NAME = "online_monitor"


async def sample_recent_answers(
    db: AsyncSession, limit: int, since_hours: int = 24
) -> list[Answer]:
    """A random sample of recently-answered, non-abstained answers.

    Abstentions are excluded on purpose: there is no answer text to score
    for faithfulness, and including them would drag the mean toward
    whatever the judge does with an empty string rather than measuring
    answer quality (SPEC.md §3.8's online monitor is a faithfulness
    time-series, not an abstention one - that's already on the Analytics page).
    """
    since = datetime.now(UTC) - timedelta(hours=since_hours)
    result = await db.execute(
        select(Answer)
        .where(Answer.created_at >= since, Answer.abstained.is_(False))
        .order_by(func.random())
        .limit(limit)
    )
    return list(result.scalars().all())


async def _rebuild_context(db: AsyncSession, answer: Answer) -> str:
    """Reconstruct the context an answer was grounded in, from the chunk ids
    its claims cite.

    Faithfulness is by definition a score *against* a context - judging
    with an empty context would return a number that looks like a metric
    but measures nothing. The stored `claims[].citations` are the only
    record of what the model actually saw, so they're the honest source.
    """
    chunk_ids: list[uuid.UUID] = []
    for claim in answer.claims or []:
        for citation in claim.get("citations", []):
            try:
                chunk_ids.append(uuid.UUID(citation))
            except (ValueError, AttributeError):
                continue  # a fabricated/malformed id, already filtered at generation
    if not chunk_ids:
        return ""
    result = await db.execute(select(Chunk).where(Chunk.id.in_(set(chunk_ids))))
    return "\n\n".join(chunk.content for chunk in result.scalars().all())


async def score_sample_faithfulness(
    db: AsyncSession, llm: LLMProvider, sample: list[Answer]
) -> list[float]:
    """Judge-score each sampled answer for faithfulness against the context
    its claims cite. Per-item failures are isolated (same rule as the eval
    runner, DECISIONS.md 2026-08-02): one bad judge call must not void the
    whole monitoring window."""
    judge = JudgeProvider(llm)
    scores: list[float] = []
    for answer in sample:
        try:
            claims = answer.claims or []
            answer_text = " ".join(c.get("text", "") for c in claims)
            context = await _rebuild_context(db, answer)
            if not answer_text.strip() or not context.strip():
                # nothing to score against - skip rather than record a
                # meaningless 0.0 that would drag the time series down
                continue
            question = (
                await db.execute(select(Query.raw_text).where(Query.id == answer.query_id))
            ).scalars().first() or ""
            result = await judge.score(
                question_id=str(answer.id),
                question=question,
                context=context,
                answer=answer_text,
                reference_answer=None,
            )
            if result.get("faithfulness") is not None:
                scores.append(float(result["faithfulness"]))
        except Exception:
            logger.exception("online monitor: judging answer %s failed", answer.id)
    return scores


async def mean_faithfulness_over(db: AsyncSession, start: datetime, end: datetime) -> float | None:
    """Mean of previously-recorded monitor scores in a window, read back off
    the spans the monitor itself writes - so the time series and the trace
    viewer are the same data, not two stores that can drift apart."""
    result = await db.execute(
        select(Span).where(
            Span.name == _MONITOR_SPAN_NAME,
            Span.started_at >= start,
            Span.started_at < end,
        )
    )
    values = [
        float(s.attributes["monitor.mean_faithfulness"])
        for s in result.scalars().all()
        if s.attributes.get("monitor.mean_faithfulness") is not None
    ]
    return sum(values) / len(values) if values else None


async def check_faithfulness_drop(db: AsyncSession, current_mean: float) -> str | None:
    """Compare the current run against the mean of the *prior* 7-day window;
    return an alert string if it dropped more than the configured points
    (SPEC.md §3.8: "alert log entry if 7-day faithfulness drops >5 points").
    Returns None when there's no prior baseline to compare against yet."""
    settings = get_settings()
    now = datetime.now(UTC)
    prior = await mean_faithfulness_over(db, now - timedelta(days=14), now - timedelta(days=7))
    if prior is None:
        return None
    drop_points = (prior - current_mean) * 100
    if drop_points > settings.ONLINE_MONITOR_DROP_ALERT_POINTS:
        return (
            f"faithfulness dropped {drop_points:.1f} points "
            f"({prior:.3f} -> {current_mean:.3f}) vs the prior 7-day window"
        )
    return None
