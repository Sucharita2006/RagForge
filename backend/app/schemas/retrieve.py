import uuid

from pydantic import BaseModel


class RetrieveRequest(BaseModel):
    question: str
    top_k: int = 10


class RetrieveCandidate(BaseModel):
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_external_id: str | None
    document_title: str | None
    content_preview: str
    dense_score: float


class RetrieveResponse(BaseModel):
    candidates: list[RetrieveCandidate]
