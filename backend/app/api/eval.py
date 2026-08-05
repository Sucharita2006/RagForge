import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.evals import EvalResult, EvalRun
from app.schemas.eval import EvalRunDetail, EvalRunOut, EvalRunRequest
from app.workers.tasks import run_eval_task

router = APIRouter(tags=["eval"])

EVAL_DATASETS_DIR = Path("/app/eval-datasets")


def _dataset_path(version: str) -> Path:
    path = EVAL_DATASETS_DIR / version / "full.jsonl"
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"no eval dataset for version {version!r}")
    return path


@router.post("/eval/run", response_model=EvalRunOut, status_code=202)
async def start_eval_run(req: EvalRunRequest, db: AsyncSession = Depends(get_db)) -> EvalRun:
    """Executes dataset x config (SPEC.md §3.7). Runs as a background Celery
    task - a full generation+judge pass over the golden set can take hours
    on CPU (DECISIONS.md 2026-08-01); this endpoint returns immediately with
    a `running` row to poll via GET /eval/runs/{id}."""
    dataset_path = _dataset_path(req.dataset_version)
    full_pipeline_ids = req.full_pipeline_ids
    if full_pipeline_ids is None and not req.full_pipeline:
        full_pipeline_ids = []  # empty set: retrieval metrics only, no generation

    run = EvalRun(
        name=req.name,
        dataset_version=req.dataset_version,
        config={
            "full_pipeline": req.full_pipeline,
            "full_pipeline_ids": full_pipeline_ids,
            "llm_provider": req.llm_provider,
        },
        status="running",
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)

    run_eval_task.delay(str(run.id), str(dataset_path), full_pipeline_ids, req.llm_provider)
    return run


@router.get("/eval/runs", response_model=list[EvalRunOut])
async def list_eval_runs(db: AsyncSession = Depends(get_db)) -> list[EvalRun]:
    result = await db.execute(select(EvalRun).order_by(EvalRun.started_at.desc()))
    return list(result.scalars().all())


@router.get("/eval/runs/{run_id}", response_model=EvalRunDetail)
async def get_eval_run(run_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> dict:
    run = await db.get(EvalRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="eval run not found")
    result = await db.execute(
        select(EvalResult).where(EvalResult.run_id == run_id).order_by(EvalResult.created_at)
    )
    results = list(result.scalars().all())
    return {
        "id": run.id,
        "name": run.name,
        "dataset_version": run.dataset_version,
        "status": run.status,
        "metrics": run.metrics,
        "error": run.error,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
        "results": results,
    }
