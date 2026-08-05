import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AppSetting(Base):
    """Small key/value store for the handful of settings that need to be
    runtime-mutable (SPEC.md §6 PATCH /settings/abstain-threshold) rather
    than a static config.py default - not in SPEC.md §5's table, added the
    same way eval_runs.metrics was (Phase 3 DECISIONS.md): small, additive,
    no spec-table entry to conflict with."""

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[dict] = mapped_column(JSONB, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class CalibrationRun(Base):
    """One run of the abstain-threshold calibration job (SPEC.md §8.5):
    sweeps ABSTAIN_THRESHOLD candidates against calibration.jsonl, records
    the full coverage/answered-precision curve (for the Settings slider) and
    which threshold was chosen."""

    __tablename__ = "calibration_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    dataset_path: Mapped[str] = mapped_column(String, nullable=False)
    curve: Mapped[list[dict]] = mapped_column(JSONB, nullable=False)
    """[{threshold, coverage, answered_precision}, ...] sorted by threshold."""
    chosen_threshold: Mapped[float] = mapped_column(Float, nullable=False)
    target_precision: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
