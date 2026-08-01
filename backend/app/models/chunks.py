import uuid
from datetime import datetime

from pgvector.sqlalchemy import HALFVEC
from sqlalchemy import Boolean, Computed, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.config import get_settings
from app.models.base import Base

settings = get_settings()


class Chunk(Base):
    """SPEC.md §5 `chunks` table.

    Phase 2 adds parent-child chunking: every document gets parent chunks
    (`is_parent=True`, `PARENT_CHUNK_SIZE` tokens, `embedding=NULL` — never
    searched directly) and child chunks (`is_parent=False`, `CHUNK_SIZE`
    tokens, `parent_id` pointing at their parent, real embedding). Dense and
    sparse search both filter to `is_parent=False`; context assembly expands
    back to the parent when that's beneficial (SPEC.md §3.2 step 7).
    """

    __tablename__ = "chunks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("chunks.id", ondelete="CASCADE"), nullable=True
    )
    is_parent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    content: Mapped[str] = mapped_column(String, nullable=False)
    context_prefix: Mapped[str | None] = mapped_column(String, nullable=True)
    """≤100-token situating prefix from contextual enrichment (Phase 2, feature-flagged)."""
    token_count: Mapped[int] = mapped_column(Integer, nullable=False)
    page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    """sha256 of normalized content — powers incremental re-ingestion (Phase 2)."""
    tsv: Mapped[str | None] = mapped_column(
        TSVECTOR, Computed("to_tsvector('english', content)", persisted=True), nullable=True
    )
    """DB-computed (GENERATED ALWAYS, see migration) — powers sparse FTS (Phase 2).
    Computed() tells the ORM to never include this column in INSERT/UPDATE;
    without it, SQLAlchemy intermittently sent an explicit NULL for it, which
    Postgres rejects for a GENERATED ALWAYS column (caught mid-reindex)."""
    embedding: Mapped[list[float] | None] = mapped_column(
        HALFVEC(settings.EMBEDDING_DIM), nullable=True
    )
    """NULL for parent chunks (is_parent=True) — they're never search candidates."""
    embedding_model: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
