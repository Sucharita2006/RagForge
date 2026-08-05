from collections import defaultdict
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends
from fastapi import Query as QueryParam
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.spans import Span
from app.observability.analytics import percentile, rate
from app.schemas.analytics import AnalyticsBucket, AnalyticsSummary, LatencyPercentiles

router = APIRouter(tags=["analytics"])

_ROOT_KIND = "CHAIN"


def _percentiles(latencies: list[int]) -> LatencyPercentiles:
    ordered = sorted(float(v) for v in latencies)
    return LatencyPercentiles(
        p50_ms=percentile(ordered, 0.50),
        p95_ms=percentile(ordered, 0.95),
        p99_ms=percentile(ordered, 0.99),
    )


@router.get("/analytics/summary", response_model=AnalyticsSummary)
async def analytics_summary(
    window_hours: int = QueryParam(24, ge=1, le=24 * 30),
    bucket_hours: int = QueryParam(1, ge=1, le=24),
    db: AsyncSession = Depends(get_db),
) -> AnalyticsSummary:
    """Latency / cost / cache / abstention over a time window (SPEC.md §3.8).

    Aggregated in Python rather than SQL: the volumes here are a portfolio
    demo's (hundreds to low thousands of spans per window), and keeping the
    percentile logic in one tested helper beats splitting it between a
    `percentile_cont` call and the unit-tested Python path.
    """
    since = datetime.now(UTC) - timedelta(hours=window_hours)
    spans = (
        (await db.execute(select(Span).where(Span.started_at >= since).order_by(Span.started_at)))
        .scalars()
        .all()
    )

    roots = [s for s in spans if s.kind == _ROOT_KIND]
    query_count = len(roots)

    cache_hits = sum(1 for s in roots if s.attributes.get("query.cache_hit") is True)
    abstentions = sum(1 for s in roots if s.attributes.get("query.abstained") is True)
    total_cost = sum(float(s.attributes.get("query.cost_usd", 0.0)) for s in roots)
    confidences = [
        float(s.attributes["query.confidence"])
        for s in roots
        if s.attributes.get("query.confidence") is not None
    ]

    by_kind: dict[str, list[int]] = defaultdict(list)
    for span in spans:
        by_kind[span.kind].append(span.latency_ms)

    buckets: list[AnalyticsBucket] = []
    bucket_delta = timedelta(hours=bucket_hours)
    grouped: dict[datetime, list[Span]] = defaultdict(list)
    for root in roots:
        elapsed = root.started_at - since
        index = int(elapsed.total_seconds() // bucket_delta.total_seconds())
        grouped[since + index * bucket_delta].append(root)

    for bucket_start in sorted(grouped):
        rows = grouped[bucket_start]
        latencies = sorted(float(r.latency_ms) for r in rows)
        buckets.append(
            AnalyticsBucket(
                bucket_start=bucket_start,
                query_count=len(rows),
                p50_ms=percentile(latencies, 0.50),
                p95_ms=percentile(latencies, 0.95),
                cache_hit_rate=rate(
                    sum(1 for r in rows if r.attributes.get("query.cache_hit") is True), len(rows)
                ),
                abstention_rate=rate(
                    sum(1 for r in rows if r.attributes.get("query.abstained") is True), len(rows)
                ),
                cost_usd=sum(float(r.attributes.get("query.cost_usd", 0.0)) for r in rows),
            )
        )

    return AnalyticsSummary(
        window_hours=window_hours,
        query_count=query_count,
        latency=_percentiles([r.latency_ms for r in roots]),
        cache_hit_rate=rate(cache_hits, query_count),
        abstention_rate=rate(abstentions, query_count),
        mean_confidence=(sum(confidences) / len(confidences)) if confidences else None,
        total_cost_usd=total_cost,
        cost_per_query_usd=(total_cost / query_count) if query_count else 0.0,
        buckets=buckets,
        by_span_kind={kind: _percentiles(values) for kind, values in sorted(by_kind.items())},
    )
