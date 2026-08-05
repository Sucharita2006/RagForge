import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ExperimentCreate(BaseModel):
    name: str
    run_a_id: uuid.UUID
    """Baseline run."""
    run_b_id: uuid.UUID
    """Candidate run."""


class ExperimentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    config_a: dict
    config_b: dict
    run_a_id: uuid.UUID
    run_b_id: uuid.UUID
    deltas: dict | None
    created_at: datetime


class ExperimentDetail(ExperimentOut):
    run_a_name: str
    run_b_name: str
