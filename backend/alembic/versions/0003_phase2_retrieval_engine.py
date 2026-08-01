"""phase 2 retrieval engine: parent-child chunking, sparse FTS, query rewrite/cache

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-01

Adds: chunks.parent_id/is_parent/context_prefix/metadata/tsv (generated,
GIN-indexed), embedding/embedding_model made nullable (NULL for parent
chunks, which are never search candidates); queries.session_id/
rewritten_text/filters/cache_hit.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "chunks",
        sa.Column(
            "parent_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("chunks.id", ondelete="CASCADE"),
            nullable=True,
        ),
    )
    op.add_column(
        "chunks",
        sa.Column("is_parent", sa.Boolean, nullable=False, server_default=sa.false()),
    )
    op.add_column("chunks", sa.Column("context_prefix", sa.String, nullable=True))
    op.add_column("chunks", sa.Column("metadata", postgresql.JSONB, nullable=True))
    op.execute(
        "ALTER TABLE chunks ADD COLUMN tsv tsvector "
        "GENERATED ALWAYS AS (to_tsvector('english', content)) STORED"
    )
    op.alter_column("chunks", "embedding", nullable=True)
    op.alter_column("chunks", "embedding_model", nullable=True)

    op.create_index("ix_chunks_parent_id", "chunks", ["parent_id"])
    op.create_index("ix_chunks_tsv", "chunks", ["tsv"], postgresql_using="gin")

    op.add_column("queries", sa.Column("session_id", sa.String, nullable=True))
    op.add_column("queries", sa.Column("rewritten_text", sa.String, nullable=True))
    op.add_column("queries", sa.Column("filters", postgresql.JSONB, nullable=True))
    op.add_column(
        "queries",
        sa.Column("cache_hit", sa.Boolean, nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_queries_session_id", "queries", ["session_id"])


def downgrade() -> None:
    op.drop_index("ix_queries_session_id", table_name="queries")
    op.drop_column("queries", "cache_hit")
    op.drop_column("queries", "filters")
    op.drop_column("queries", "rewritten_text")
    op.drop_column("queries", "session_id")

    op.drop_index("ix_chunks_tsv", table_name="chunks")
    op.drop_index("ix_chunks_parent_id", table_name="chunks")
    op.alter_column("chunks", "embedding_model", nullable=False)
    op.alter_column("chunks", "embedding", nullable=False)
    op.drop_column("chunks", "tsv")
    op.drop_column("chunks", "metadata")
    op.drop_column("chunks", "context_prefix")
    op.drop_column("chunks", "is_parent")
    op.drop_column("chunks", "parent_id")
