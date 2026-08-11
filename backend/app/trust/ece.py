"""Expected Calibration Error + reliability diagram (SPEC.md §7.2, §8.5).

Confidence is only useful if it *means* something: a batch of answers rated
0.7 should be right about 70% of the time. ECE measures exactly that gap.

Scope note - ECE is computed over **answered** items only, not abstentions.
That is the standard selective-prediction framing and it matters here: our
`compute_confidence` returns a hard 0.0 whenever the generator reports
insufficient context, so a correctly-abstained unanswerable item would
enter the lowest bin as a "correct" outcome and make calibration look
terrible precisely when the trust layer is behaving well. Abstentions are
not predictions; they are declines to predict, and they are already scored
by `abstention_recall_unanswerable` / `answered_precision`.
"""


def reliability_bins(pairs: list[tuple[float, bool]], n_bins: int = 10) -> list[dict]:
    """Bucket (confidence, was_correct) pairs into equal-width bins.

    Equal-width rather than equal-count (quantile) bins: the target is a
    fixed 0.10 threshold on the standard ECE definition, and quantile
    binning would silently change what that number means.
    """
    if not pairs:
        return []

    bins: list[dict] = []
    for i in range(n_bins):
        low = i / n_bins
        high = (i + 1) / n_bins
        # last bin is closed on the right so confidence == 1.0 lands somewhere
        members = [
            (c, ok) for c, ok in pairs if (low <= c < high) or (i == n_bins - 1 and c == 1.0)
        ]
        if not members:
            continue
        mean_confidence = sum(c for c, _ in members) / len(members)
        accuracy = sum(1 for _, ok in members if ok) / len(members)
        bins.append(
            {
                "bin_low": low,
                "bin_high": high,
                "count": len(members),
                "mean_confidence": mean_confidence,
                "accuracy": accuracy,
                "gap": abs(mean_confidence - accuracy),
            }
        )
    return bins


def expected_calibration_error(pairs: list[tuple[float, bool]], n_bins: int = 10) -> float:
    """Weighted mean |confidence - accuracy| across bins (SPEC.md §7.2 target
    <= 0.10). Empty input returns 0.0 - "no predictions" is not miscalibration."""
    bins = reliability_bins(pairs, n_bins)
    if not bins:
        return 0.0
    total = sum(b["count"] for b in bins)
    return sum(b["count"] / total * b["gap"] for b in bins)


def maximum_calibration_error(pairs: list[tuple[float, bool]], n_bins: int = 10) -> float:
    """Worst single-bin gap. Reported alongside ECE because a low ECE can
    hide one badly-miscalibrated bin when that bin holds few items."""
    bins = reliability_bins(pairs, n_bins)
    return max((b["gap"] for b in bins), default=0.0)
