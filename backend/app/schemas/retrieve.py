import uuid

from pydantic import BaseModel


class RetrieveRequest(BaseModel):
    question: str
    top_k: int = 10
    document_id: uuid.UUID | None = None


class RetrieveCandidate(BaseModel):
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_external_id: str | None
    document_title: str | None
    content_preview: str
    dense_score: float | None
    dense_rank: int | None
    sparse_score: float | None
    sparse_rank: int | None
    rrf_score: float | None
    rerank_score: float | None


class RetrieveResponse(BaseModel):
    candidates: list[RetrieveCandidate]
