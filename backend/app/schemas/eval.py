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
    llm_provider: str = "ollama"
    """'ollama' (self-hosted, default) | 'gemini' (needs GOOGLE_API_KEY) |
    'openrouter' (needs OPENROUTER_API_KEY) - lets a long full-pipeline run
    swap off local CPU/RAM without changing production /query's provider
    (DECISIONS.md 2026-08-03, 2026-08-06)."""


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
