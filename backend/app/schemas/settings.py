from pydantic import BaseModel


class SettingsOut(BaseModel):
    abstain_threshold: float
    confidence_weights: dict[str, float]
    minicheck_support_threshold: float
    calibration_curve: list[dict] | None = None
    """Most recent calibration run's threshold/coverage/precision curve
    (SPEC.md §8.5), None if the calibration job has never run."""


class AbstainThresholdPatch(BaseModel):
    threshold: float
