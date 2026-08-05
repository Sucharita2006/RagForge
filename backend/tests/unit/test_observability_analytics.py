from app.observability.analytics import percentile, rate
from app.observability.cost import compute_cost_usd


def test_percentile_empty_is_zero_not_an_error() -> None:
    """An empty time window is a normal dashboard state, not a failure."""
    assert percentile([], 0.95) == 0.0


def test_percentile_single_value() -> None:
    assert percentile([42.0], 0.50) == 42.0
    assert percentile([42.0], 0.99) == 42.0


def test_percentile_returns_an_actually_observed_value() -> None:
    """Nearest-rank, not interpolated: p95 should be a real observation so it
    can be matched back to a specific trace."""
    values = [float(v) for v in range(1, 101)]  # 1..100
    assert percentile(values, 0.95) in values
    assert percentile(values, 0.50) in values


def test_percentile_is_monotonic_in_q() -> None:
    values = [float(v) for v in range(1, 101)]
    assert percentile(values, 0.50) <= percentile(values, 0.95) <= percentile(values, 0.99)


def test_percentile_p100_is_the_max() -> None:
    values = [1.0, 5.0, 9.0]
    assert percentile(values, 1.0) == 9.0


def test_rate_zero_denominator_is_zero() -> None:
    assert rate(0, 0) == 0.0


def test_rate_basic() -> None:
    assert rate(1, 4) == 0.25


def test_compute_cost_usd_self_hosted_is_free() -> None:
    assert compute_cost_usd("ollama", 100_000, 50_000) == 0.0


def test_compute_cost_usd_hosted_model_priced_per_million() -> None:
    # gemini-flash-latest: $0.30/1M in, $2.50/1M out
    cost = compute_cost_usd("gemini-flash-latest", 1_000_000, 1_000_000)
    assert abs(cost - 2.80) < 1e-9


def test_compute_cost_usd_unknown_model_is_zero_not_an_error() -> None:
    """A missing price entry must never break a live query."""
    assert compute_cost_usd("some-model-we-never-priced", 1_000, 1_000) == 0.0


def test_compute_cost_usd_handles_none_tokens() -> None:
    assert compute_cost_usd("gemini-flash-latest", None, None) == 0.0
