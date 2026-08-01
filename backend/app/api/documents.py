import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.session import get_db
from app.models.documents import Document
from app.schemas.documents import DocumentOut, IngestResponse
from app.workers.tasks import reingest_document_task

router = APIRouter(tags=["documents"])
settings = get_settings()


@router.get("/documents", response_model=list[DocumentOut])
async def list_documents(db: AsyncSession = Depends(get_db)) -> list[Document]:
    result = await db.execute(select(Document).order_by(Document.created_at.desc()))
    return list(result.scalars().all())


@router.get("/documents/{document_id}", response_model=DocumentOut)
async def get_document(document_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> Document:
    document = await db.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="document not found")
    return document


@router.delete("/documents/{document_id}", status_code=204)
async def delete_document(document_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> None:
    document = await db.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="document not found")
    await db.delete(document)
    await db.commit()


@router.post("/documents/{document_id}/reindex", response_model=IngestResponse)
async def reindex_document(
    document_id: uuid.UUID, file: UploadFile, db: AsyncSession = Depends(get_db)
) -> IngestResponse:
    """Incremental re-ingestion (SPEC.md §6): re-embeds only chunks whose
    content changed; unchanged chunks reuse their existing embedding."""
    document = await db.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="document not found")

    upload_dir = Path(settings.UPLOAD_DIR)
    upload_dir.mkdir(parents=True, exist_ok=True)
    dest = upload_dir / f"{document.id}_{file.filename or document.filename}"
    with dest.open("wb") as f:
        shutil.copyfileobj(file.file, f)

    document.status = "pending"
    await db.commit()

    reingest_document_task.delay(str(document.id), str(dest))
    return IngestResponse(document_id=document.id, status=document.status)
