import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.retrieval.dense import dense_search
from app.retrieval.fusion import FusedCandidate, reciprocal_rank_fusion
from app.retrieval.rerankers.minilm import get_reranker_provider
from app.retrieval.sparse import sparse_search

settings = get_settings()


async def retrieve(
    db: AsyncSession,
    query_text: str,
    query_embedding: list[float],
    document_id: uuid.UUID | None = None,
) -> list[FusedCandidate]:
    """Full retrieval pipeline (SPEC.md §3.2 steps 3-6): dense + sparse ->
    RRF fusion -> cross-encoder rerank -> top RERANK_CANDIDATES, reordered
    by rerank score. Powers both /api/retrieve (debug, all four score types)
    and /api/query (context assembly consumes the top slice)."""
    dense_results = await dense_search(
        db, query_embedding, settings.DENSE_TOP_K, settings.HNSW_EF_SEARCH, document_id
    )
    sparse_results = await sparse_search(db, query_text, settings.SPARSE_TOP_K, document_id)

    fused = reciprocal_rank_fusion(dense_results, sparse_results, settings.RRF_K)
    candidates = fused[: settings.RERANK_CANDIDATES]

    if candidates:
        reranker = get_reranker_provider()
        scores = reranker.rerank(query_text, [c.chunk.content for c in candidates])
        for candidate, score in zip(candidates, scores, strict=True):
            candidate.rerank_score = score
        candidates.sort(
            key=lambda c: c.rerank_score if c.rerank_score is not None else float("-inf"),
            reverse=True,
        )

    return candidates
