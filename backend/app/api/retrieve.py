from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.session import get_db
from app.models.documents import Document
from app.providers.embeddings.bge_small import get_embedding_provider
from app.retrieval.dense import dense_search
from app.schemas.retrieve import RetrieveCandidate, RetrieveRequest, RetrieveResponse

router = APIRouter(tags=["retrieve"])
settings = get_settings()


@router.post("/retrieve", response_model=RetrieveResponse)
async def retrieve(req: RetrieveRequest, db: AsyncSession = Depends(get_db)) -> RetrieveResponse:
    """Debug endpoint (SPEC.md §3.2): dense score only in Phase 1 — sparse rank,
    RRF score, and rerank score are added in Phase 2 alongside the Retrieval
    Inspector page."""
    embedder = get_embedding_provider()
    query_embedding = embedder.embed_query(req.question)
    results = await dense_search(db, query_embedding, req.top_k, settings.HNSW_EF_SEARCH)

    candidates = []
    for chunk, score in results:
        document = await db.get(Document, chunk.document_id)
        candidates.append(
            RetrieveCandidate(
                chunk_id=chunk.id,
                document_id=chunk.document_id,
                document_external_id=document.external_id if document else None,
                document_title=document.title if document else None,
                content_preview=chunk.content[:200],
                dense_score=score,
            )
        )
    return RetrieveResponse(candidates=candidates)
