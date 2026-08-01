import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Query(Base):
    """SPEC.md §5 `queries` table."""

    __tablename__ = "queries"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[str | None] = mapped_column(String, nullable=True)
    """Client-generated id grouping a conversation for query-rewrite context (Phase 2)."""
    raw_text: Mapped[str] = mapped_column(String, nullable=False)
    rewritten_text: Mapped[str | None] = mapped_column(String, nullable=True)
    filters: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    cache_hit: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    trace_id: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
