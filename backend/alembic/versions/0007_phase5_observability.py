"""phase 5 observability: spans, experiments

Revision ID: 0007
Revises: 0006
Create Date: 2026-08-06

Adds `spans` (SPEC.md §5/§3.8 - one OpenInference span per pipeline step,
written by the Postgres OTel exporter) and `experiments` (§5/§3.9 page 5 -
A/B comparison of two eval runs with bootstrap-CI deltas).

Index note: SPEC.md §5 calls for `spans(trace_id)`; also indexing
`spans(started_at)` since the Traces list page and the analytics summary
both scan by time window.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "spans",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("span_id", sa.String(16), nullable=False),
        sa.Column("trace_id", sa.String(32), nullable=False),
        sa.Column("parent_span_id", sa.String(16), nullable=True),
        sa.Column("kind", sa.String, nullable=False),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("latency_ms", sa.Integer, nullable=False),
        sa.Column("attributes", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("status", sa.String, nullable=False, server_default="OK"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_spans_trace_id", "spans", ["trace_id"])
    op.create_index("ix_spans_started_at", "spans", ["started_at"])

    op.create_table(
        "experiments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("config_a", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("config_b", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column(
            "run_a_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("eval_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "run_b_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("eval_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("deltas", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_experiments_created_at", "experiments", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_experiments_created_at", table_name="experiments")
    op.drop_table("experiments")

    op.drop_index("ix_spans_started_at", table_name="spans")
    op.drop_index("ix_spans_trace_id", table_name="spans")
    op.drop_table("spans")
