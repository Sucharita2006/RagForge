from app.trust.ece import (
    expected_calibration_error,
    maximum_calibration_error,
    reliability_bins,
)


def test_ece_empty_is_zero() -> None:
    """No predictions is not miscalibration."""
    assert expected_calibration_error([]) == 0.0


def test_ece_perfectly_calibrated_is_zero() -> None:
    """In the 0.8-0.9 bin, exactly 80% correct -> gap ~0."""
    pairs = [(0.85, True)] * 8 + [(0.85, False)] * 2
    assert expected_calibration_error(pairs) < 0.06


def test_ece_maximally_overconfident_is_one() -> None:
    """Confidence 1.0 on answers that are all wrong."""
    pairs = [(1.0, False)] * 10
    assert expected_calibration_error(pairs) == 1.0


def test_ece_maximally_underconfident_is_one() -> None:
    pairs = [(0.0, True)] * 10
    assert expected_calibration_error(pairs) == 1.0


def test_ece_is_weighted_by_bin_population() -> None:
    """A tiny badly-calibrated bin must not dominate a large well-calibrated one."""
    good = [(0.95, True)] * 95 + [(0.95, False)] * 5  # bin ~calibrated
    bad = [(0.05, True)]  # 1 item, badly miscalibrated
    ece = expected_calibration_error(good + bad)
    assert ece < 0.05


def test_maximum_calibration_error_surfaces_the_worst_bin() -> None:
    """MCE catches what a population-weighted ECE can hide."""
    good = [(0.95, True)] * 95 + [(0.95, False)] * 5
    bad = [(0.05, True)]
    assert maximum_calibration_error(good + bad) > 0.9


def test_reliability_bins_confidence_of_one_is_not_dropped() -> None:
    """Off-by-one guard: c == 1.0 must land in the last bin, not vanish."""
    bins = reliability_bins([(1.0, True)], n_bins=10)
    assert sum(b["count"] for b in bins) == 1


def test_reliability_bins_skip_empty_bins() -> None:
    bins = reliability_bins([(0.05, True), (0.95, True)], n_bins=10)
    assert len(bins) == 2


def test_reliability_bins_accuracy_and_confidence_are_per_bin() -> None:
    pairs = [(0.15, True), (0.15, False), (0.85, True), (0.85, True)]
    bins = {round(b["bin_low"], 1): b for b in reliability_bins(pairs, n_bins=10)}
    assert bins[0.1]["accuracy"] == 0.5
    assert bins[0.8]["accuracy"] == 1.0
