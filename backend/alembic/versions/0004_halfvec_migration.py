"""embedding storage: vector -> halfvec (measured before/after)

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-01

implementation-plan.md §2.E: Phase 1's baseline-v0 used plain float32
`vector` on purpose so this migration is a measured before/after, not an
unmeasured starting point. `halfvec` (fp16) roughly halves embedding storage
with <1% recall degradation on normalized embeddings per the research in
document/research-latency-optimization.md. Requires dropping and recreating
the HNSW index with `halfvec_cosine_ops` (the vector_cosine_ops operator
class doesn't apply to the new column type).
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

EMBEDDING_DIM = 384


def upgrade() -> None:
    op.drop_index("ix_chunks_embedding_hnsw", table_name="chunks")
    op.execute(
        f"ALTER TABLE chunks ALTER COLUMN embedding TYPE halfvec({EMBEDDING_DIM}) "
        f"USING embedding::halfvec({EMBEDDING_DIM})"
    )
    op.create_index(
        "ix_chunks_embedding_hnsw",
        "chunks",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_with={"m": 16, "ef_construction": 200},
        postgresql_ops={"embedding": "halfvec_cosine_ops"},
    )


def downgrade() -> None:
    op.drop_index("ix_chunks_embedding_hnsw", table_name="chunks")
    op.execute(
        f"ALTER TABLE chunks ALTER COLUMN embedding TYPE vector({EMBEDDING_DIM}) "
        f"USING embedding::vector({EMBEDDING_DIM})"
    )
    op.create_index(
        "ix_chunks_embedding_hnsw",
        "chunks",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_with={"m": 16, "ef_construction": 200},
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )
