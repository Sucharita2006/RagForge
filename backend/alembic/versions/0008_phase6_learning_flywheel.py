"""phase 6 learning flywheel: feedback, training_pairs, model_registry, failure_clusters

Revision ID: 0008
Revises: 0007
Create Date: 2026-08-06

Adds the learning-loop tables (SPEC.md §5/§3.5). Also seeds the baseline
`reranker` row in `model_registry` as `active`, so the registry pointer has
a valid target from the moment it exists - otherwise the first request after
this migration would find no active model and have to fall back silently,
which is exactly the kind of implicit state this table exists to remove.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

_BASELINE_RERANKER = "cross-encoder/ms-marco-MiniLM-L-6-v2"


def upgrade() -> None:
    op.create_table(
        "feedback",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "answer_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("answers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("rating", sa.Integer, nullable=False),
        sa.Column("correction", sa.String, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_feedback_answer_id", "feedback", ["answer_id"])

    op.create_table(
        "training_pairs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("query", sa.String, nullable=False),
        sa.Column(
            "positive_chunk_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("chunks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("hard_negative_chunk_ids", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("source", sa.String, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_training_pairs_source", "training_pairs", ["source"])

    op.create_table(
        "model_registry",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("kind", sa.String, nullable=False),
        sa.Column("base_model", sa.String, nullable=False),
        sa.Column("artifact_path", sa.String, nullable=True),
        sa.Column("train_config", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("eval_metrics", postgresql.JSONB, nullable=True),
        sa.Column("status", sa.String, nullable=False, server_default="candidate"),
        sa.Column("promoted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_model_registry_kind", "model_registry", ["kind"])
    # Only one row per kind may be active - enforced in the DB rather than
    # only in the promote endpoint, so a bad write can't leave two "active"
    # models and make which one loads depend on row order.
    op.create_index(
        "uq_model_registry_one_active_per_kind",
        "model_registry",
        ["kind"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )

    op.create_table(
        "failure_clusters",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("window", sa.String, nullable=False),
        sa.Column("cluster_label", sa.String, nullable=False),
        sa.Column("size", sa.Integer, nullable=False),
        sa.Column("sample_query_ids", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("suggested_action", sa.String, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.execute(
        sa.text(
            """
            INSERT INTO model_registry
                (id, kind, base_model, artifact_path, train_config, status, promoted_at)
            VALUES
                (gen_random_uuid(), 'reranker', :base, NULL, '{"baseline": true}'::jsonb,
                 'active', now())
            """
        ).bindparams(base=_BASELINE_RERANKER)
    )


def downgrade() -> None:
    op.drop_table("failure_clusters")
    op.drop_index("uq_model_registry_one_active_per_kind", table_name="model_registry")
    op.drop_index("ix_model_registry_kind", table_name="model_registry")
    op.drop_table("model_registry")
    op.drop_index("ix_training_pairs_source", table_name="training_pairs")
    op.drop_table("training_pairs")
    op.drop_index("ix_feedback_answer_id", table_name="feedback")
    op.drop_table("feedback")
