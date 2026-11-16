import uuid

from pydantic import BaseModel


class QueryRequest(BaseModel):
    question: str
    session_id: str | None = None
    """Client-generated id grouping a conversation, enabling query rewrite (Phase 2)."""


class ClaimOut(BaseModel):
    text: str
    citations: list[str]
    support_prob: float | None = None
    """MiniCheck entailment probability against its cited (or fallback) source span."""
    verdict: str | None = None
    """'supported' | 'unsupported' | 'unscored'."""


class SourceOut(BaseModel):
    document_external_id: str | None
    title: str | None
    rerank_score: float | None


class PassageOut(BaseModel):
    chunk_id: str
    document_external_id: str | None
    title: str | None
    text: str


class QueryResponse(BaseModel):
    query_id: uuid.UUID
    answer_id: uuid.UUID
    claims: list[ClaimOut]
    """Empty when `abstained` (SPEC.md §3.3: an abstention response carries
    no partial answer, only the sources that were found)."""
    insufficient_context: bool
    """Raw signal: the model itself judged the context insufficient. Kept
    distinct from `abstained` - the trust layer's confidence-gated decision,
    which can also fire on a real (but weakly grounded) answer."""
    confidence: float
    abstained: bool
    sources: list[SourceOut]
    passages: list[PassageOut] = []
    """The text of every chunk a returned claim cites, in first-cited order,
    so a reader can see what each sentence was checked against. Empty when
    `abstained`, like `claims`."""
    trace_id: str | None
    model: str
    latency_ms: int | None
    cache_hit: bool = False
    rewritten_question: str | None = None
