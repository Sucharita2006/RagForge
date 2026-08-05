from app.trust.abstain import should_abstain


def test_should_abstain_below_threshold() -> None:
    assert should_abstain(0.4, threshold=0.55) is True


def test_should_abstain_at_threshold_does_not_abstain() -> None:
    assert should_abstain(0.55, threshold=0.55) is False


def test_should_abstain_well_above_threshold() -> None:
    assert should_abstain(0.9, threshold=0.55) is False


def test_should_abstain_zero_confidence_always_abstains_for_any_positive_threshold() -> None:
    assert should_abstain(0.0, threshold=0.01) is True
