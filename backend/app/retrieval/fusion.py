import uuid
from dataclasses import dataclass

from app.models.chunks import Chunk


@dataclass
class FusedCandidate:
    chunk: Chunk
    rrf_score: float
    dense_score: float | None = None
    dense_rank: int | None = None
    sparse_score: float | None = None
    sparse_rank: int | None = None
    rerank_score: float | None = None
    """Populated by the reranking stage (retrieval/rerankers/), not fusion itself."""


def reciprocal_rank_fusion(
    dense_results: list[tuple[Chunk, float]],
    sparse_results: list[tuple[Chunk, float]],
    rrf_k: int,
) -> list[FusedCandidate]:
    """Reciprocal Rank Fusion (SPEC.md §3.2 step 5): score(d) = sum over each
    ranked list containing d of 1/(rrf_k + rank), rank 1-indexed. Cost is
    negligible relative to the search/rerank stages (implementation-plan.md
    §2.E2, confirmed by OpenSearch/Chroma/Azure AI Search docs) — no need to
    benchmark separately.

    Returns candidates sorted by fused RRF score, each carrying its dense/
    sparse rank and score for the Retrieval Inspector's four-score view.
    """
    chunks_by_id: dict[uuid.UUID, Chunk] = {}
    dense_rank: dict[uuid.UUID, int] = {}
    dense_score: dict[uuid.UUID, float] = {}
    sparse_rank: dict[uuid.UUID, int] = {}
    sparse_score: dict[uuid.UUID, float] = {}

    for i, (chunk, score) in enumerate(dense_results, start=1):
        chunks_by_id[chunk.id] = chunk
        dense_rank[chunk.id] = i
        dense_score[chunk.id] = score

    for i, (chunk, score) in enumerate(sparse_results, start=1):
        chunks_by_id[chunk.id] = chunk
        sparse_rank[chunk.id] = i
        sparse_score[chunk.id] = score

    def rrf_score(chunk_id: uuid.UUID) -> float:
        score = 0.0
        if chunk_id in dense_rank:
            score += 1.0 / (rrf_k + dense_rank[chunk_id])
        if chunk_id in sparse_rank:
            score += 1.0 / (rrf_k + sparse_rank[chunk_id])
        return score

    ranked_ids = sorted(chunks_by_id, key=rrf_score, reverse=True)

    return [
        FusedCandidate(
            chunk=chunks_by_id[cid],
            rrf_score=rrf_score(cid),
            dense_score=dense_score.get(cid),
            dense_rank=dense_rank.get(cid),
            sparse_score=sparse_score.get(cid),
            sparse_rank=sparse_rank.get(cid),
        )
        for cid in ranked_ids
    ]
