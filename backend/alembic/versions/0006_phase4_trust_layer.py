"""phase 4 trust layer: answers.confidence/abstained, app_settings, calibration_runs

Revision ID: 0006
Revises: 0005
Create Date: 2026-08-03

Adds confidence/abstained columns to `answers` (SPEC.md §5), a small
app_settings key/value table for the runtime-mutable abstain threshold
(SPEC.md §6 PATCH /settings/abstain-threshold - not itself in §5's table,
added the same way eval_runs.metrics was in Phase 3: small, additive, no
spec-table entry to conflict with), and calibration_runs (SPEC.md §8.5's
threshold-fitting job history + curve, for the Settings slider).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("answers", sa.Column("confidence", sa.Float, nullable=True))
    op.add_column(
        "answers",
        sa.Column("abstained", sa.Boolean, nullable=False, server_default=sa.false()),
    )

    op.create_table(
        "app_settings",
        sa.Column("key", sa.String, primary_key=True),
        sa.Column("value", postgresql.JSONB, nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
    )

    op.create_table(
        "calibration_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("dataset_path", sa.String, nullable=False),
        sa.Column("curve", postgresql.JSONB, nullable=False),
        sa.Column("chosen_threshold", sa.Float, nullable=False),
        sa.Column("target_precision", sa.Float, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("calibration_runs")
    op.drop_table("app_settings")
    op.drop_column("answers", "abstained")
    op.drop_column("answers", "confidence")
