from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.documents import Document
from app.providers.embeddings.bge_small import get_embedding_provider
from app.retrieval.pipeline import retrieve as run_retrieval_pipeline
from app.schemas.retrieve import RetrieveCandidate, RetrieveRequest, RetrieveResponse

router = APIRouter(tags=["retrieve"])


@router.post("/retrieve", response_model=RetrieveResponse)
async def retrieve(req: RetrieveRequest, db: AsyncSession = Depends(get_db)) -> RetrieveResponse:
    """Debug endpoint (SPEC.md §3.2): every candidate with dense score,
    sparse rank, RRF score, and rerank score — powers the Retrieval
    Inspector page (Phase 2)."""
    embedder = get_embedding_provider()
    query_embedding = embedder.embed_query(req.question)
    fused = await run_retrieval_pipeline(db, req.question, query_embedding, req.document_id)

    candidates = []
    for f in fused[: req.top_k]:
        document = await db.get(Document, f.chunk.document_id)
        candidates.append(
            RetrieveCandidate(
                chunk_id=f.chunk.id,
                document_id=f.chunk.document_id,
                document_external_id=document.external_id if document else None,
                document_title=document.title if document else None,
                content_preview=f.chunk.content[:200],
                dense_score=f.dense_score,
                dense_rank=f.dense_rank,
                sparse_score=f.sparse_score,
                sparse_rank=f.sparse_rank,
                rrf_score=f.rrf_score,
                rerank_score=f.rerank_score,
            )
        )
    return RetrieveResponse(candidates=candidates)
