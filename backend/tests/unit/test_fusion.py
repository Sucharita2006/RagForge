import uuid

import pytest

from app.models.chunks import Chunk
from app.retrieval.fusion import reciprocal_rank_fusion


def make_chunk(name: str) -> Chunk:
    chunk = Chunk(
        id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        content=name,
        token_count=10,
        content_hash="x" * 64,
    )
    return chunk


def test_rrf_known_input_matches_hand_computed_scores() -> None:
    a, b, c, d = make_chunk("a"), make_chunk("b"), make_chunk("c"), make_chunk("d")
    dense = [(a, 0.9), (b, 0.8), (c, 0.7)]  # ranks 1,2,3
    sparse = [(b, 5.0), (c, 4.0), (d, 3.0)]  # ranks 1,2,3
    rrf_k = 60

    fused = reciprocal_rank_fusion(dense, sparse, rrf_k)
    scores = {f.chunk.content: f.rrf_score for f in fused}

    assert scores["a"] == pytest.approx(1 / 61)
    assert scores["b"] == pytest.approx(1 / 62 + 1 / 61)
    assert scores["c"] == pytest.approx(1 / 63 + 1 / 62)
    assert scores["d"] == pytest.approx(1 / 63)
    # b appears in both lists near the top -> should win overall
    assert [f.chunk.content for f in fused] == ["b", "c", "a", "d"]


def test_rrf_preserves_rank_and_score_metadata_for_inspector() -> None:
    a, b = make_chunk("a"), make_chunk("b")
    dense = [(a, 0.9)]
    sparse = [(b, 5.0)]
    fused = reciprocal_rank_fusion(dense, sparse, rrf_k=60)
    by_content = {f.chunk.content: f for f in fused}

    assert by_content["a"].dense_rank == 1
    assert by_content["a"].dense_score == 0.9
    assert by_content["a"].sparse_rank is None
    assert by_content["b"].sparse_rank == 1
    assert by_content["b"].sparse_score == 5.0
    assert by_content["b"].dense_rank is None


def test_rrf_empty_inputs_returns_empty() -> None:
    assert reciprocal_rank_fusion([], [], rrf_k=60) == []
