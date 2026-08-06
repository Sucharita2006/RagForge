import pytest

from app.learning.clustering import classify_failure
from app.learning.promotion import PromotionRejected, evaluate_promotion


def _metrics(values: dict[str, float], n: int = 12) -> dict[str, dict[str, float]]:
    """n questions all scoring the same - a clean, unambiguous signal."""
    return {f"q{i}": dict(values) for i in range(n)}


def test_promotion_accepts_a_real_significant_improvement() -> None:
    active = _metrics({"ndcg@10": 0.70, "hit_rate": 0.80})
    candidate = _metrics({"ndcg@10": 0.85, "hit_rate": 0.90})
    verdict = evaluate_promotion(active, candidate)
    assert "ndcg@10" in verdict["improved_metrics"]


def test_promotion_rejects_a_regression() -> None:
    active = _metrics({"ndcg@10": 0.85, "hit_rate": 0.90})
    candidate = _metrics({"ndcg@10": 0.60, "hit_rate": 0.70})
    with pytest.raises(PromotionRejected, match="regressed"):
        evaluate_promotion(active, candidate)


def test_promotion_rejects_no_change() -> None:
    """The core gate: identical performance must NOT promote."""
    same = _metrics({"ndcg@10": 0.80, "hit_rate": 0.85})
    with pytest.raises(PromotionRejected, match="not measurably better"):
        evaluate_promotion(same, dict(same))


def test_promotion_rejects_noise_that_averages_upward() -> None:
    """A candidate that wins on some questions and loses on others by a
    similar margin is not an improvement, however the mean lands."""
    active = {f"q{i}": {"ndcg@10": 0.5 + (0.3 if i % 2 else -0.3)} for i in range(12)}
    candidate = {f"q{i}": {"ndcg@10": 0.5 + (-0.3 if i % 2 else 0.3)} for i in range(12)}
    with pytest.raises(PromotionRejected):
        evaluate_promotion(active, candidate)


def test_promotion_rejects_mixed_win_and_regression() -> None:
    """Trading NDCG for hit-rate is not an upgrade."""
    active = _metrics({"ndcg@10": 0.60, "hit_rate": 0.90})
    candidate = _metrics({"ndcg@10": 0.85, "hit_rate": 0.60})
    with pytest.raises(PromotionRejected, match="regressed"):
        evaluate_promotion(active, candidate)


def test_promotion_rejects_when_no_gate_metrics_present() -> None:
    """Runs that share no retrieval metrics can't decide a retrieval model."""
    active = _metrics({"faithfulness": 0.5})
    candidate = _metrics({"faithfulness": 0.9})
    with pytest.raises(PromotionRejected, match="no gate metrics"):
        evaluate_promotion(active, candidate)


def test_promotion_rejected_carries_gate_detail() -> None:
    """A refusal must explain itself, not just say no."""
    same = _metrics({"ndcg@10": 0.80, "hit_rate": 0.85})
    with pytest.raises(PromotionRejected) as exc:
        evaluate_promotion(same, dict(same))
    assert "ndcg@10" in exc.value.detail
    assert exc.value.detail["ndcg@10"]["significant"] is False


def test_classify_failure_no_candidates_is_knowledge_gap() -> None:
    assert (
        classify_failure(
            abstained=True, has_citations=False, corpus_has_candidates=False, parser_fallback=False
        )
        == "knowledge_gap"
    )


def test_classify_failure_parser_fallback_takes_priority_over_retrieval() -> None:
    assert (
        classify_failure(
            abstained=True, has_citations=False, corpus_has_candidates=True, parser_fallback=True
        )
        == "parsing_gap"
    )


def test_classify_failure_abstention_with_candidates_is_retrieval_miss() -> None:
    assert (
        classify_failure(
            abstained=True, has_citations=False, corpus_has_candidates=True, parser_fallback=False
        )
        == "retrieval_miss"
    )


def test_classify_failure_answered_without_citations_is_generation_error() -> None:
    assert (
        classify_failure(
            abstained=False, has_citations=False, corpus_has_candidates=True, parser_fallback=False
        )
        == "generation_error"
    )
