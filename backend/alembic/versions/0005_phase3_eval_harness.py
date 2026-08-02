"""phase 3 eval harness: eval_datasets, eval_runs, eval_results

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-01

Adds the eval-harness tables (SPEC.md §5): eval_datasets (a lightweight
registry row per golden-set version), eval_runs (one harness execution
against a named config + dataset version, with an aggregate `metrics`
summary), eval_results (per-question drill-down rows for a run).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "eval_datasets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("version", sa.String, nullable=False, unique=True),
        sa.Column("path", sa.String, nullable=False),
        sa.Column("size", sa.Integer, nullable=False),
        sa.Column("composition", postgresql.JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "eval_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("dataset_version", sa.String, nullable=False),
        sa.Column("config", postgresql.JSONB, nullable=False),
        sa.Column("git_sha", sa.String, nullable=True),
        sa.Column("status", sa.String, nullable=False, server_default="running"),
        sa.Column("metrics", postgresql.JSONB, nullable=True),
        sa.Column("error", sa.String, nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_eval_runs_dataset_version", "eval_runs", ["dataset_version"])
    op.create_index("ix_eval_runs_started_at", "eval_runs", ["started_at"])

    op.create_table(
        "eval_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("eval_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("question_id", sa.String, nullable=False),
        sa.Column("question_type", sa.String, nullable=False),
        sa.Column("metrics", postgresql.JSONB, nullable=False),
        sa.Column("retrieved", postgresql.JSONB, nullable=False),
        sa.Column("answer", postgresql.JSONB, nullable=False),
        sa.Column("judge_notes", sa.String, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_eval_results_run_id", "eval_results", ["run_id"])


def downgrade() -> None:
    op.drop_index("ix_eval_results_run_id", table_name="eval_results")
    op.drop_table("eval_results")

    op.drop_index("ix_eval_runs_started_at", table_name="eval_runs")
    op.drop_index("ix_eval_runs_dataset_version", table_name="eval_runs")
    op.drop_table("eval_runs")

    op.drop_table("eval_datasets")
