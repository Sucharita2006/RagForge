import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class FeedbackCreate(BaseModel):
    answer_id: uuid.UUID
    rating: int = Field(description="+1 or -1", ge=-1, le=1)
    correction: str | None = None


class FeedbackOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    answer_id: uuid.UUID
    rating: int
    correction: str | None
    created_at: datetime


class ModelOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: str
    base_model: str
    artifact_path: str | None
    train_config: dict
    eval_metrics: dict | None
    status: str
    promoted_at: datetime | None
    created_at: datetime


class PromoteRequest(BaseModel):
    run_active_id: uuid.UUID
    """Eval run for the currently-active model (baseline)."""
    run_candidate_id: uuid.UUID
    """Eval run for this candidate."""


class PromoteResponse(BaseModel):
    promoted: bool
    model: ModelOut | None = None
    improved_metrics: list[str] = []
    gate: dict = {}
    reason: str | None = None


class FinetuneRequest(BaseModel):
    max_pairs: int | None = None
    epochs: int = 1
    batch_size: int = 16


class FailureClusterOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    window: str
    cluster_label: str
    size: int
    sample_query_ids: list
    suggested_action: str
    created_at: datetime
