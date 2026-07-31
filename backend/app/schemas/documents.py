import uuid

from pydantic import BaseModel, ConfigDict


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    filename: str
    title: str | None
    external_id: str | None
    status: str
    parser: str | None


class IngestResponse(BaseModel):
    document_id: uuid.UUID
    status: str
