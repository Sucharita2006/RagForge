from app.evals.bootstrap import paired_bootstrap_delta_ci
from app.evals.experiments import compare_runs, numeric_metrics_by_question


class FakeResult:
    """Stands in for an EvalResult row without touching the DB."""

    def __init__(self, question_id: str, metrics: dict) -> None:
        self.question_id = question_id
        self.metrics = metrics


def test_paired_bootstrap_empty_is_not_significant() -> None:
    result = paired_bootstrap_delta_ci([])
    assert result["n"] == 0
    assert result["significant"] is False


def test_paired_bootstrap_consistent_improvement_is_significant() -> None:
    """Every question improves by ~0.2 - the CI should exclude zero."""
    pairs = [(0.5, 0.7), (0.6, 0.8), (0.4, 0.6), (0.55, 0.75), (0.45, 0.65), (0.5, 0.7)]
    result = paired_bootstrap_delta_ci(pairs)
    assert result["delta"] > 0
    assert result["ci_low"] > 0
    assert result["significant"] is True


def test_paired_bootstrap_noise_is_not_significant() -> None:
    """Deltas that straddle zero must not be called a win."""
    pairs = [(0.5, 0.6), (0.6, 0.5), (0.4, 0.45), (0.55, 0.5), (0.5, 0.52), (0.45, 0.4)]
    result = paired_bootstrap_delta_ci(pairs)
    assert result["ci_low"] < 0 < result["ci_high"]
    assert result["significant"] is False


def test_paired_bootstrap_beats_unpaired_on_correlated_data() -> None:
    """The reason pairing exists: when questions differ wildly in difficulty
    but the candidate consistently wins, the paired CI should detect it where
    an unpaired one drowns in between-question variance."""
    from app.evals.bootstrap import bootstrap_delta_ci

    baseline = [0.1, 0.9, 0.2, 0.8, 0.3, 0.7, 0.15, 0.85]
    candidate = [b + 0.05 for b in baseline]
    paired = paired_bootstrap_delta_ci(list(zip(baseline, candidate, strict=True)))
    unpaired = bootstrap_delta_ci(baseline, candidate)
    assert paired["significant"] is True
    assert (paired["ci_high"] - paired["ci_low"]) < (unpaired["ci_high"] - unpaired["ci_low"])


def test_paired_bootstrap_is_deterministic_given_a_seed() -> None:
    pairs = [(0.5, 0.7), (0.6, 0.8), (0.4, 0.6)]
    assert paired_bootstrap_delta_ci(pairs) == paired_bootstrap_delta_ci(pairs)


def test_numeric_metrics_by_question_coerces_bools() -> None:
    rows = [FakeResult("q1", {"hit_rate": 1.0, "abstained": True, "note": "ignored"})]
    flattened = numeric_metrics_by_question(rows)
    assert flattened["q1"]["abstained"] == 1.0
    assert "note" not in flattened["q1"]


def test_compare_runs_only_uses_questions_present_in_both() -> None:
    """A run with holes (per-item failure isolation) must not bias the delta."""
    a = {"q1": {"ndcg": 0.5}, "q2": {"ndcg": 0.6}, "q3": {"ndcg": 0.9}}
    b = {"q1": {"ndcg": 0.7}, "q2": {"ndcg": 0.8}}  # q3 missing
    comparison = compare_runs(a, b)
    assert comparison["ndcg"]["n"] == 2


def test_compare_runs_marks_lower_is_better_metrics_correctly() -> None:
    """A drop in unsupported_claim_rate is an improvement, not a regression."""
    a = {f"q{i}": {"unsupported_claim_rate": 0.5} for i in range(6)}
    b = {f"q{i}": {"unsupported_claim_rate": 0.2} for i in range(6)}
    comparison = compare_runs(a, b)
    result = comparison["unsupported_claim_rate"]
    assert result["delta"] < 0
    assert result["lower_is_better"] is True
    assert result["improved"] is True


def test_compare_runs_higher_is_better_regression_is_not_improved() -> None:
    a = {f"q{i}": {"ndcg": 0.9} for i in range(6)}
    b = {f"q{i}": {"ndcg": 0.5} for i in range(6)}
    result = compare_runs(a, b)["ndcg"]
    assert result["significant"] is True
    assert result["improved"] is False


def test_compare_runs_no_shared_questions_returns_empty() -> None:
    assert compare_runs({"q1": {"ndcg": 0.5}}, {"q9": {"ndcg": 0.5}}) == {}
