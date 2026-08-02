import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class EvalRunRequest(BaseModel):
    name: str
    dataset_version: str = "v1"
    full_pipeline: bool = True
    """If False, only retrieval metrics run (fast, no generation)."""
    full_pipeline_ids: list[str] | None = None
    """If set, only these question ids get generation+judge; every other
    item still gets retrieval metrics. Overrides `full_pipeline`."""


class EvalRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    dataset_version: str
    status: str
    metrics: dict | None
    error: str | None
    started_at: datetime
    finished_at: datetime | None


class EvalResultOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    question_id: str
    question_type: str
    metrics: dict
    retrieved: dict
    answer: dict
    judge_notes: str | None


class EvalRunDetail(EvalRunOut):
    results: list[EvalResultOut]
