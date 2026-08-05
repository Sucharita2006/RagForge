import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Span(Base):
    """SPEC.md §5 `spans` table / §3.8: one OpenInference span per pipeline
    step, persisted by the Postgres OTel exporter (app/observability/exporter.py).

    `span_id`/`trace_id`/`parent_span_id` are OTel's own hex ids (16 and 32
    chars), not UUIDs - kept as strings so a trace can be correlated with
    `queries.trace_id`/`answers.trace_id`, which already store the same
    32-hex format from Phase 1.
    """

    __tablename__ = "spans"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    span_id: Mapped[str] = mapped_column(String(16), nullable=False)
    trace_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    parent_span_id: Mapped[str | None] = mapped_column(String(16), nullable=True)
    kind: Mapped[str] = mapped_column(String, nullable=False)
    """OpenInference span kind: CHAIN | RETRIEVER | RERANKER | LLM |
    GUARDRAIL | EVALUATOR | EMBEDDING."""
    name: Mapped[str] = mapped_column(String, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    attributes: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    """Token counts, computed cost, retrieved doc ids/scores, model names."""
    status: Mapped[str] = mapped_column(String, nullable=False, default="OK")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Experiment(Base):
    """SPEC.md §5 `experiments` table / §3.9 page 5: an A/B comparison of two
    eval runs, with per-metric deltas and bootstrap CIs (SPEC.md §7.2's
    "every improvement reported as a delta vs baseline" rule, made a
    first-class object rather than a manual diff of two baseline files)."""

    __tablename__ = "experiments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String, nullable=False)
    config_a: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    config_b: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    run_a_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("eval_runs.id", ondelete="CASCADE"), nullable=False
    )
    run_b_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("eval_runs.id", ondelete="CASCADE"), nullable=False
    )
    deltas: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    """{metric: {delta, ci_low, ci_high, significant, n_a, n_b}} - `significant`
    is the promotion gate's rule: the 95% CI on the delta excludes 0."""
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
