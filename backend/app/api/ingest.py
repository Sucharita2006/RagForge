import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, Form, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.session import get_db
from app.models.documents import Document
from app.schemas.documents import IngestResponse
from app.workers.tasks import ingest_document_task

router = APIRouter(tags=["ingest"])
settings = get_settings()


@router.post("/ingest", response_model=IngestResponse)
async def ingest_file(
    file: UploadFile,
    title: str | None = Form(default=None),
    external_id: str | None = Form(default=None),
    db: AsyncSession = Depends(get_db),
) -> IngestResponse:
    document = Document(
        filename=file.filename or "upload.pdf",
        mime=file.content_type or "application/pdf",
        title=title,
        external_id=external_id,
    )
    db.add(document)
    await db.commit()
    await db.refresh(document)

    upload_dir = Path(settings.UPLOAD_DIR)
    upload_dir.mkdir(parents=True, exist_ok=True)
    dest = upload_dir / f"{document.id}_{document.filename}"
    with dest.open("wb") as f:
        shutil.copyfileobj(file.file, f)

    ingest_document_task.delay(str(document.id), str(dest))
    return IngestResponse(document_id=document.id, status=document.status)
