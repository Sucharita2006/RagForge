from app.evals.schemas import GoldenItem
from app.trust.calibration import choose_threshold, sweep_thresholds


def make_item(item_id: str, unanswerable: bool) -> GoldenItem:
    return GoldenItem(id=item_id, type="single_hop", question="q", unanswerable=unanswerable)


def test_sweep_thresholds_zero_threshold_answers_everything() -> None:
    scored = [(make_item("a", False), 0.9), (make_item("b", True), 0.1)]
    curve = sweep_thresholds(scored, n_steps=11)
    assert curve[0]["threshold"] == 0.0
    assert curve[0]["coverage"] == 1.0


def test_sweep_thresholds_precision_at_a_threshold_excluding_the_unanswerable_item() -> None:
    scored = [(make_item("a", False), 0.9), (make_item("b", True), 0.1)]
    curve = sweep_thresholds(scored, n_steps=11)
    point = next(p for p in curve if abs(p["threshold"] - 0.2) < 1e-9)
    assert point["coverage"] == 0.5
    assert point["answered_precision"] == 1.0


def test_sweep_thresholds_empty_input_is_zero_coverage_throughout() -> None:
    curve = sweep_thresholds([], n_steps=5)
    assert all(p["coverage"] == 0.0 for p in curve)


def test_choose_threshold_picks_lowest_meeting_target() -> None:
    curve = [
        {"threshold": 0.0, "coverage": 1.0, "answered_precision": 0.5},
        {"threshold": 0.5, "coverage": 0.6, "answered_precision": 0.92},
        {"threshold": 1.0, "coverage": 0.1, "answered_precision": 1.0},
    ]
    assert choose_threshold(curve, target_precision=0.90) == 0.5


def test_choose_threshold_falls_back_to_one_when_target_unreachable() -> None:
    curve = [{"threshold": 0.0, "coverage": 1.0, "answered_precision": 0.5}]
    assert choose_threshold(curve, target_precision=0.90) == 1.0
