import uuid

from opentelemetry import trace
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.retrieval.dense import dense_search
from app.retrieval.fusion import FusedCandidate, reciprocal_rank_fusion
from app.retrieval.rerankers.minilm import get_reranker_provider
from app.retrieval.rerankers.registry import active_reranker_path
from app.retrieval.sparse import sparse_search

settings = get_settings()
tracer = trace.get_tracer(__name__)


async def retrieve(
    db: AsyncSession,
    query_text: str,
    query_embedding: list[float],
    document_id: uuid.UUID | None = None,
    reranker_path: str | None = None,
) -> list[FusedCandidate]:
    """Full retrieval pipeline (SPEC.md §3.2 steps 3-6): dense + sparse ->
    RRF fusion -> cross-encoder rerank -> top RERANK_CANDIDATES, reordered
    by rerank score. Powers both /api/retrieve (debug, all four score types)
    and /api/query (context assembly consumes the top slice).

    `reranker_path` overrides the registry's active model for this call only.
    It exists so an eval run can score a *candidate* model without promoting
    it first - otherwise the A/B gate would require shipping the model it is
    supposed to be deciding on (Phase 6)."""
    dense_results = await dense_search(
        db, query_embedding, settings.DENSE_TOP_K, settings.HNSW_EF_SEARCH, document_id
    )
    sparse_results = await sparse_search(db, query_text, settings.SPARSE_TOP_K, document_id)

    fused = reciprocal_rank_fusion(dense_results, sparse_results, settings.RRF_K)
    candidates = fused[: settings.RERANK_CANDIDATES]

    if candidates:
        reranker = get_reranker_provider(reranker_path or await active_reranker_path(db))
        with tracer.start_as_current_span(
            "rerank",
            attributes={
                "openinference.span.kind": "RERANKER",
                "reranker.model_name": reranker.model_name,
                "reranker.input_document_count": len(candidates),
                "reranker.top_k": settings.FINAL_TOP_K,
            },
        ) as rerank_span:
            scores = reranker.rerank(query_text, [c.chunk.content for c in candidates])
            for candidate, score in zip(candidates, scores, strict=True):
                candidate.rerank_score = score
            candidates.sort(
                key=lambda c: c.rerank_score if c.rerank_score is not None else float("-inf"),
                reverse=True,
            )
            # top-k doc ids/scores only: the full 50-candidate list would
            # bloat every stored span for detail nobody reads in a waterfall.
            for i, candidate in enumerate(candidates[: settings.FINAL_TOP_K]):
                prefix = f"retrieval.documents.{i}.document"
                rerank_span.set_attribute(f"{prefix}.id", str(candidate.chunk.id))
                rerank_span.set_attribute(f"{prefix}.score", candidate.rerank_score or 0.0)

    return candidates
