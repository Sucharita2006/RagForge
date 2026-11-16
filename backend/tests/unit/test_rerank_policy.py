from app.models.chunks import Chunk
from app.retrieval.fusion import FusedCandidate
from app.retrieval.pipeline import apply_rerank


def candidates(*scores: float | None) -> list[FusedCandidate]:
    """In fusion order: the first has the highest RRF score."""
    return [
        FusedCandidate(chunk=Chunk(content=str(i)), rrf_score=1.0 / (i + 1), rerank_score=s)
        for i, s in enumerate(scores)
    ]


def order(result: list[FusedCandidate]) -> list[str]:
    return [c.chunk.content for c in result]


def test_without_a_threshold_the_cross_encoder_order_is_final() -> None:
    assert order(apply_rerank(candidates(-1.0, 4.0, None, 2.0), None)) == ["1", "3", "0", "2"]


def test_with_a_threshold_only_confident_candidates_move() -> None:
    # 1 and 3 clear 3.0 and go first in reranker order; 0 and 2 keep fusion order
    assert order(apply_rerank(candidates(-1.0, 4.0, 2.5, 6.0), 3.0)) == ["3", "1", "0", "2"]
    # nothing clears the bar: fusion order stands
    assert order(apply_rerank(candidates(-1.0, 2.0, 1.0), 3.0)) == ["0", "1", "2"]
