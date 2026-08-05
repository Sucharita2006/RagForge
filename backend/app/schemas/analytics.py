from datetime import datetime

from pydantic import BaseModel


class LatencyPercentiles(BaseModel):
    p50_ms: float
    p95_ms: float
    p99_ms: float


class AnalyticsBucket(BaseModel):
    """One time bucket of the Analytics page's time series (SPEC.md §3.8)."""

    bucket_start: datetime
    query_count: int
    p50_ms: float
    p95_ms: float
    cache_hit_rate: float
    abstention_rate: float
    cost_usd: float


class AnalyticsSummary(BaseModel):
    window_hours: int
    query_count: int
    latency: LatencyPercentiles
    cache_hit_rate: float
    abstention_rate: float
    mean_confidence: float | None
    total_cost_usd: float
    cost_per_query_usd: float
    buckets: list[AnalyticsBucket]
    by_span_kind: dict[str, LatencyPercentiles]
    """Per-stage latency breakdown - which pipeline step dominates p95."""
