import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.evals.experiments import numeric_metrics_by_question
from app.learning.promotion import PromotionRejected, evaluate_promotion
from app.models.answers import Answer
from app.models.evals import EvalResult, EvalRun
from app.models.learning import FailureCluster, Feedback, ModelRegistry
from app.schemas.learning import (
    FailureClusterOut,
    FeedbackCreate,
    FeedbackOut,
    FinetuneRequest,
    ModelOut,
    PromoteRequest,
    PromoteResponse,
)
from app.workers.tasks import finetune_reranker_task

router = APIRouter(tags=["learning"])


@router.post("/feedback", response_model=FeedbackOut, status_code=201)
async def create_feedback(req: FeedbackCreate, db: AsyncSession = Depends(get_db)) -> Feedback:
    """Thumbs up/down + optional correction (SPEC.md §3.5). Trace linkage is
    implicit through `answers.trace_id`, so feedback joins straight to the
    span waterfall that produced it."""
    if req.rating not in (-1, 1):
        raise HTTPException(status_code=422, detail="rating must be +1 or -1")
    if await db.get(Answer, req.answer_id) is None:
        raise HTTPException(status_code=404, detail="answer not found")

    feedback = Feedback(
        answer_id=req.answer_id, rating=req.rating, correction=req.correction or None
    )
    db.add(feedback)
    await db.commit()
    await db.refresh(feedback)
    return feedback


@router.get("/feedback", response_model=list[FeedbackOut])
async def list_feedback(limit: int = 100, db: AsyncSession = Depends(get_db)) -> list[Feedback]:
    result = await db.execute(select(Feedback).order_by(Feedback.created_at.desc()).limit(limit))
    return list(result.scalars().all())


@router.get("/models", response_model=list[ModelOut])
async def list_models(db: AsyncSession = Depends(get_db)) -> list[ModelRegistry]:
    result = await db.execute(select(ModelRegistry).order_by(ModelRegistry.created_at.desc()))
    return list(result.scalars().all())


@router.post("/finetune/reranker", status_code=202)
async def finetune_reranker(req: FinetuneRequest) -> dict:
    """Queue a reranker fine-tune (SPEC.md §6). Returns immediately - training
    runs in the Celery worker, which is also the only process that loads the
    training dependency stack."""
    task = finetune_reranker_task.delay(req.max_pairs, req.epochs, req.batch_size)
    return {"status": "queued", "task_id": task.id}


async def _metrics_by_question(db: AsyncSession, run_id: uuid.UUID) -> dict:
    results = list(
        (await db.execute(select(EvalResult).where(EvalResult.run_id == run_id))).scalars().all()
    )
    return numeric_metrics_by_question(results)


@router.post("/models/{model_id}/promote", response_model=PromoteResponse)
async def promote_model(
    model_id: uuid.UUID, req: PromoteRequest, db: AsyncSession = Depends(get_db)
) -> PromoteResponse:
    """Promote a candidate **only if** the A/B gate passes (SPEC.md §3.5).

    The endpoint enforces the gate rather than trusting the caller: a
    promotion that can be forced by passing a flag is not a gate.
    """
    candidate = await db.get(ModelRegistry, model_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="model not found")
    if candidate.status == "active":
        raise HTTPException(status_code=409, detail="model is already active")

    for run_id in (req.run_active_id, req.run_candidate_id):
        if await db.get(EvalRun, run_id) is None:
            raise HTTPException(status_code=404, detail=f"eval run {run_id} not found")

    metrics_active = await _metrics_by_question(db, req.run_active_id)
    metrics_candidate = await _metrics_by_question(db, req.run_candidate_id)
    if not metrics_active or not metrics_candidate:
        raise HTTPException(status_code=422, detail="both runs need per-question results")

    try:
        verdict = evaluate_promotion(metrics_active, metrics_candidate)
    except PromotionRejected as rejected:
        # 200, not an error status: the gate working correctly and refusing a
        # weak candidate is a successful outcome of asking, not a failure of
        # the request.
        candidate.eval_metrics = {"gate": rejected.detail, "promoted": False}
        await db.commit()
        return PromoteResponse(promoted=False, reason=rejected.reason, gate=rejected.detail)

    # Retire the incumbent before activating, so the partial-unique index
    # ("one active per kind") is never transiently violated.
    await db.execute(
        update(ModelRegistry)
        .where(ModelRegistry.kind == candidate.kind, ModelRegistry.status == "active")
        .values(status="retired")
    )
    candidate.status = "active"
    candidate.promoted_at = datetime.now(UTC)
    candidate.eval_metrics = {"gate": verdict["gate"], "promoted": True}
    await db.commit()
    await db.refresh(candidate)

    return PromoteResponse(
        promoted=True,
        model=ModelOut.model_validate(candidate),
        improved_metrics=verdict["improved_metrics"],
        gate=verdict["gate"],
    )


@router.get("/failures/clusters", response_model=list[FailureClusterOut])
async def list_failure_clusters(db: AsyncSession = Depends(get_db)) -> list[FailureCluster]:
    result = await db.execute(
        select(FailureCluster).order_by(FailureCluster.created_at.desc()).limit(50)
    )
    return list(result.scalars().all())
