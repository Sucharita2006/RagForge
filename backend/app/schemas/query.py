import uuid

from pydantic import BaseModel


class QueryRequest(BaseModel):
    question: str


class ClaimOut(BaseModel):
    text: str
    citations: list[str]


class QueryResponse(BaseModel):
    query_id: uuid.UUID
    answer_id: uuid.UUID
    claims: list[ClaimOut]
    insufficient_context: bool
    trace_id: str | None
    model: str
    latency_ms: int | None
