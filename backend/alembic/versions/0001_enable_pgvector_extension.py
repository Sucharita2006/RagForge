"""enable pgvector extension

Revision ID: 0001
Revises:
Create Date: 2026-07-30

DECISIONS.md 2026-07-30: pgvector pinned >=0.8.2 (buffer-overflow CVE fix,
required for the hnsw.iterative_scan filtering architecture in
implementation-plan.md §2.E1). The postgres image used in docker-compose.yml
is pgvector/pgvector:pg16, which ships an up-to-date pgvector build.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")


def downgrade() -> None:
    op.execute("DROP EXTENSION IF EXISTS vector")
