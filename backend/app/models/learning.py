import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Feedback(Base):
    """SPEC.md §5 `feedback` / §3.5: thumbs up/down + optional correction,
    linked to the answer (and through it, the trace) it refers to."""

    __tablename__ = "feedback"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    answer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("answers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    """+1 or -1."""
    correction: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TrainingPair(Base):
    """SPEC.md §5 `training_pairs` / §3.5: a (query, positive chunk, hard
    negatives) example for reranker/embedder fine-tuning.

    `source` records provenance - 'feedback' (mined from a thumbs-down),
    'synthetic' (generated from the corpus), or 'mined' (hard negatives
    mined against an existing positive). Kept explicit so a training run can
    be reproduced from, or restricted to, a known subset.
    """

    __tablename__ = "training_pairs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    query: Mapped[str] = mapped_column(String, nullable=False)
    positive_chunk_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("chunks.id", ondelete="CASCADE"), nullable=False
    )
    hard_negative_chunk_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    source: Mapped[str] = mapped_column(String, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ModelRegistry(Base):
    """SPEC.md §5 `model_registry` / §3.5: every fine-tune run, its artifact,
    and its measured eval metrics.

    `status` drives the hot-swap pointer: exactly one row per `kind` may be
    'active' at a time; the rest are 'candidate' or 'retired'. The active
    row is what `get_reranker_provider()` loads, so promotion is a DB write
    rather than a redeploy.
    """

    __tablename__ = "model_registry"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    kind: Mapped[str] = mapped_column(String, nullable=False, index=True)
    """embedder | reranker."""
    base_model: Mapped[str] = mapped_column(String, nullable=False)
    artifact_path: Mapped[str | None] = mapped_column(String, nullable=True)
    """None for the built-in baseline row, which points at the HF model id."""
    train_config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    eval_metrics: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="candidate")
    """candidate | active | retired."""
    promoted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class FailureCluster(Base):
    """SPEC.md §5 `failure_clusters` / §3.9 page 8: grouped failure modes over
    a time window, each with a suggested action."""

    __tablename__ = "failure_clusters"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    window: Mapped[str] = mapped_column(String, nullable=False)
    cluster_label: Mapped[str] = mapped_column(String, nullable=False)
    """retrieval_miss | generation_error | parsing_gap | knowledge_gap."""
    size: Mapped[int] = mapped_column(Integer, nullable=False)
    sample_query_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    suggested_action: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
