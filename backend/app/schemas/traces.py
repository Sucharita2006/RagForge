import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class SpanOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    span_id: str
    trace_id: str
    parent_span_id: str | None
    kind: str
    name: str
    started_at: datetime
    ended_at: datetime
    latency_ms: int
    attributes: dict
    status: str


class TraceSummary(BaseModel):
    """One row of the Traces list page - a trace rolled up to its root."""

    trace_id: str
    root_name: str
    started_at: datetime
    latency_ms: int
    span_count: int
    status: str
    question: str | None = None
    cache_hit: bool | None = None
    abstained: bool | None = None
    cost_usd: float | None = None


class TraceDetail(BaseModel):
    trace_id: str
    spans: list[SpanOut]
    """Ordered by started_at, so the frontend can render a waterfall directly."""
    question: str | None = None
    total_latency_ms: int
    total_cost_usd: float
