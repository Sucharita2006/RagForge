import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Document(Base):
    """SPEC.md §5 `documents` table (Phase 1 subset — gcs_path/corpus_version land in Phase 8/2)."""

    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    filename: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str | None] = mapped_column(String, nullable=True)
    external_id: Mapped[str | None] = mapped_column(String, nullable=True)
    """e.g. arXiv id, for the seeded demo corpus."""
    source_url: Mapped[str | None] = mapped_column(String, nullable=True)
    mime: Mapped[str] = mapped_column(String, nullable=False, default="application/pdf")
    parser: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    """pending | processing | ready | failed"""
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
