from collections.abc import Sequence


def percentile(sorted_values: Sequence[float], q: float) -> float:
    """Nearest-rank percentile over an already-sorted sequence.

    Deliberately not numpy's linear-interpolation default: for latency
    percentiles a p95 that equals an actually-observed request is easier to
    reason about (and to match against a trace) than one interpolated
    between two neighbours. Empty input is 0.0 rather than an error - an
    empty time window is a normal state for a dashboard, not a failure.
    """
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return float(sorted_values[0])
    rank = max(1, min(len(sorted_values), round(q * len(sorted_values) + 0.5)))
    return float(sorted_values[rank - 1])


def rate(numerator: int, denominator: int) -> float:
    """Share in [0,1]; an empty denominator is 0.0, not a ZeroDivisionError."""
    return numerator / denominator if denominator else 0.0
