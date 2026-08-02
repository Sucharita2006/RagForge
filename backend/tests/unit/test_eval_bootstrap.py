import pytest

from app.evals.bootstrap import bootstrap_ci, bootstrap_delta_ci


def test_bootstrap_ci_mean_matches_simple_average() -> None:
    result = bootstrap_ci([1.0, 1.0, 1.0, 0.0], n_resamples=500)
    assert result["mean"] == pytest.approx(0.75)
    assert result["n"] == 4
    assert result["ci_low"] <= result["mean"] <= result["ci_high"]


def test_bootstrap_ci_empty_input_is_zeroed() -> None:
    result = bootstrap_ci([])
    assert result == {"mean": 0.0, "ci_low": 0.0, "ci_high": 0.0, "n": 0}


def test_bootstrap_ci_constant_values_has_zero_width_interval() -> None:
    result = bootstrap_ci([0.5, 0.5, 0.5], n_resamples=200)
    assert result["ci_low"] == pytest.approx(0.5)
    assert result["ci_high"] == pytest.approx(0.5)


def test_bootstrap_ci_is_deterministic_given_a_seed() -> None:
    a = bootstrap_ci([0.1, 0.9, 0.4, 0.6, 0.2], n_resamples=300, seed=7)
    b = bootstrap_ci([0.1, 0.9, 0.4, 0.6, 0.2], n_resamples=300, seed=7)
    assert a == b


def test_bootstrap_delta_ci_matches_simple_mean_difference() -> None:
    result = bootstrap_delta_ci([0.5, 0.5], [0.9, 0.9], n_resamples=500)
    assert result["delta"] == pytest.approx(0.4)
    assert result["ci_low"] <= result["delta"] <= result["ci_high"]


def test_bootstrap_delta_ci_empty_input_is_zeroed() -> None:
    result = bootstrap_delta_ci([], [1.0])
    assert result == {"delta": 0.0, "ci_low": 0.0, "ci_high": 0.0}
