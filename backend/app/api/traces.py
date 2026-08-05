from fastapi import APIRouter, Depends, HTTPException
from fastapi import Query as QueryParam
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.queries import Query
from app.models.spans import Span
from app.schemas.traces import SpanOut, TraceDetail, TraceSummary

router = APIRouter(tags=["traces"])

_ROOT_KIND = "CHAIN"


@router.get("/traces", response_model=list[TraceSummary])
async def list_traces(
    limit: int = QueryParam(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> list[TraceSummary]:
    """Traces list (SPEC.md §3.9 page 6), rolled up to one row per trace.

    Driven off the root CHAIN span rather than a GROUP BY over all spans:
    the root already carries the end-to-end latency and the query-level
    attributes (cache hit, abstention, cost) the list column-renders, so
    this stays a single indexed scan plus one count.
    """
    roots = (
        (
            await db.execute(
                select(Span)
                .where(Span.kind == _ROOT_KIND)
                .order_by(Span.started_at.desc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    if not roots:
        return []

    trace_ids = [root.trace_id for root in roots]

    count_rows = (
        await db.execute(
            select(Span.trace_id, func.count(Span.id))
            .where(Span.trace_id.in_(trace_ids))
            .group_by(Span.trace_id)
        )
    ).all()
    counts: dict[str, int] = {trace_id: count for trace_id, count in count_rows}

    question_rows = (
        await db.execute(
            select(Query.trace_id, Query.raw_text).where(Query.trace_id.in_(trace_ids))
        )
    ).all()
    questions: dict[str, str] = {
        trace_id: text for trace_id, text in question_rows if trace_id is not None
    }

    return [
        TraceSummary(
            trace_id=root.trace_id,
            root_name=root.name,
            started_at=root.started_at,
            latency_ms=root.latency_ms,
            span_count=counts.get(root.trace_id, 1),
            status=root.status,
            question=questions.get(root.trace_id),
            cache_hit=root.attributes.get("query.cache_hit"),
            abstained=root.attributes.get("query.abstained"),
            cost_usd=root.attributes.get("query.cost_usd"),
        )
        for root in roots
    ]


@router.get("/traces/{trace_id}", response_model=TraceDetail)
async def get_trace(trace_id: str, db: AsyncSession = Depends(get_db)) -> TraceDetail:
    """Every span in one trace, time-ordered for a waterfall render."""
    spans = (
        (await db.execute(select(Span).where(Span.trace_id == trace_id).order_by(Span.started_at)))
        .scalars()
        .all()
    )
    if not spans:
        raise HTTPException(status_code=404, detail="trace not found")

    question = (
        (await db.execute(select(Query.raw_text).where(Query.trace_id == trace_id)))
        .scalars()
        .first()
    )

    root = next((s for s in spans if s.kind == _ROOT_KIND), None)
    return TraceDetail(
        trace_id=trace_id,
        spans=[SpanOut.model_validate(s) for s in spans],
        question=question,
        # fall back to the widest span when a trace has no CHAIN root (e.g. a
        # background job's spans, which aren't request-scoped)
        total_latency_ms=root.latency_ms if root else max(s.latency_ms for s in spans),
        total_cost_usd=sum(float(s.attributes.get("llm.cost_usd", 0.0)) for s in spans),
    )
