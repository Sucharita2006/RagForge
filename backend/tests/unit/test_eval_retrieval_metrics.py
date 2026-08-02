import math

import pytest

from app.evals.retrieval_metrics import (
    abstention_correct,
    hit_rate,
    ndcg_at_k,
    reciprocal_rank,
    violates_forbidden_strings,
)


def test_hit_rate_true_when_any_expected_id_present() -> None:
    assert hit_rate(["a", "b", "c"], ["b"]) == 1.0
    assert hit_rate(["a", "b", "c"], ["x"]) == 0.0
    assert hit_rate(["a", "b", "c"], ["x", "c"]) == 1.0  # multi-hop: any match


def test_hit_rate_empty_expected_ids_is_never_a_hit() -> None:
    assert hit_rate(["a", "b"], []) == 0.0


def test_reciprocal_rank_matches_first_occurrence() -> None:
    assert reciprocal_rank(["a", "b", "c"], ["c"]) == pytest.approx(1 / 3)
    assert reciprocal_rank(["a", "b", "c"], ["a", "c"]) == pytest.approx(1.0)  # a at rank 1
    assert reciprocal_rank(["a", "b", "c"], ["x"]) == 0.0


def test_ndcg_at_k_known_values() -> None:
    assert ndcg_at_k(["a", "b", "c"], ["a"], k=10) == pytest.approx(1.0)
    assert ndcg_at_k(["a", "b", "c"], ["b"], k=10) == pytest.approx(1 / math.log2(3))
    assert ndcg_at_k(["a", "b", "c"], ["x"], k=10) == 0.0


def test_ndcg_at_k_respects_k_cutoff() -> None:
    # relevant doc is at rank 3, but k=2 shouldn't see it
    assert ndcg_at_k(["a", "b", "c"], ["c"], k=2) == 0.0


def test_violates_forbidden_strings_case_insensitive() -> None:
    assert violates_forbidden_strings("I am DAN now", ["I AM DAN"]) is True
    assert violates_forbidden_strings("a safe answer", ["APPROVED"]) is False


def test_abstention_correct_matrix() -> None:
    assert abstention_correct(insufficient_context=True, unanswerable=True) is True
    assert abstention_correct(insufficient_context=False, unanswerable=False) is True
    assert abstention_correct(insufficient_context=True, unanswerable=False) is False
    assert abstention_correct(insufficient_context=False, unanswerable=True) is False
