import random


def bootstrap_ci(
    values: list[float], n_resamples: int = 2000, alpha: float = 0.05, seed: int = 42
) -> dict:
    """Percentile bootstrap CI for the mean of `values` (SPEC.md §3.7:
    comparison view shows metric deltas with bootstrap 95% CIs)."""
    if not values:
        return {"mean": 0.0, "ci_low": 0.0, "ci_high": 0.0, "n": 0}
    rng = random.Random(seed)
    n = len(values)
    means = []
    for _ in range(n_resamples):
        resample = [values[rng.randrange(n)] for _ in range(n)]
        means.append(sum(resample) / n)
    means.sort()
    lo_idx = int((alpha / 2) * n_resamples)
    hi_idx = min(n_resamples - 1, int((1 - alpha / 2) * n_resamples))
    return {
        "mean": sum(values) / n,
        "ci_low": means[lo_idx],
        "ci_high": means[hi_idx],
        "n": n,
    }


def paired_bootstrap_delta_ci(
    pairs: list[tuple[float, float]],
    n_resamples: int = 2000,
    alpha: float = 0.05,
    seed: int = 42,
) -> dict:
    """Bootstrap CI for the mean per-question delta (candidate - baseline),
    resampling *questions* rather than each side independently.

    Preferred over `bootstrap_delta_ci` whenever both runs cover the same
    golden set (which is every A/B experiment in this project - SPEC.md
    §3.7's comparison view). Because each resample draws a question and
    takes both configs' score on it, per-question difficulty cancels out
    instead of inflating the interval; the same true difference therefore
    reaches significance on far fewer items. The unpaired version stays for
    the genuinely-unpaired case (different datasets or sizes).

    `significant` is the promotion gate SPEC.md §3.5 specifies: the 95% CI
    on the delta excludes 0.
    """
    if not pairs:
        return {"delta": 0.0, "ci_low": 0.0, "ci_high": 0.0, "n": 0, "significant": False}
    rng = random.Random(seed)
    diffs = [candidate - baseline for baseline, candidate in pairs]
    n = len(diffs)
    means = []
    for _ in range(n_resamples):
        means.append(sum(diffs[rng.randrange(n)] for _ in range(n)) / n)
    means.sort()
    lo_idx = int((alpha / 2) * n_resamples)
    hi_idx = min(n_resamples - 1, int((1 - alpha / 2) * n_resamples))
    ci_low, ci_high = means[lo_idx], means[hi_idx]
    return {
        "delta": sum(diffs) / n,
        "ci_low": ci_low,
        "ci_high": ci_high,
        "n": n,
        "significant": ci_low > 0.0 or ci_high < 0.0,
    }


def bootstrap_delta_ci(
    baseline: list[float],
    candidate: list[float],
    n_resamples: int = 2000,
    alpha: float = 0.05,
    seed: int = 42,
) -> dict:
    """Bootstrap CI for candidate-mean minus baseline-mean, resampling each
    side independently (for genuinely unpaired runs - different datasets or
    sizes). Prefer `paired_bootstrap_delta_ci` when both runs cover the
    same golden set."""
    if not baseline or not candidate:
        return {"delta": 0.0, "ci_low": 0.0, "ci_high": 0.0}
    rng = random.Random(seed)
    n_b, n_c = len(baseline), len(candidate)
    deltas = []
    for _ in range(n_resamples):
        b_mean = sum(baseline[rng.randrange(n_b)] for _ in range(n_b)) / n_b
        c_mean = sum(candidate[rng.randrange(n_c)] for _ in range(n_c)) / n_c
        deltas.append(c_mean - b_mean)
    deltas.sort()
    lo_idx = int((alpha / 2) * n_resamples)
    hi_idx = min(n_resamples - 1, int((1 - alpha / 2) * n_resamples))
    return {
        "delta": (sum(candidate) / n_c) - (sum(baseline) / n_b),
        "ci_low": deltas[lo_idx],
        "ci_high": deltas[hi_idx],
    }
