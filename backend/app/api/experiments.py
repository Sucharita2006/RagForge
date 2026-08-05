import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.evals.experiments import compare_runs, numeric_metrics_by_question
from app.models.evals import EvalResult, EvalRun
from app.models.spans import Experiment
from app.schemas.experiments import ExperimentCreate, ExperimentDetail, ExperimentOut

router = APIRouter(tags=["experiments"])


async def _results_for(db: AsyncSession, run_id: uuid.UUID) -> list[EvalResult]:
    return list(
        (await db.execute(select(EvalResult).where(EvalResult.run_id == run_id))).scalars().all()
    )


@router.post("/experiments", response_model=ExperimentOut, status_code=201)
async def create_experiment(
    req: ExperimentCreate, db: AsyncSession = Depends(get_db)
) -> Experiment:
    """Compare two eval runs with paired bootstrap CIs (SPEC.md §3.9 page 5).

    Computed synchronously: the comparison is pure arithmetic over rows
    already in the DB (no model calls), so it returns in well under a
    second - unlike the eval runs themselves, which are Celery-queued.
    """
    run_a = await db.get(EvalRun, req.run_a_id)
    run_b = await db.get(EvalRun, req.run_b_id)
    if run_a is None or run_b is None:
        raise HTTPException(status_code=404, detail="one or both eval runs not found")

    results_a = await _results_for(db, req.run_a_id)
    results_b = await _results_for(db, req.run_b_id)
    if not results_a or not results_b:
        raise HTTPException(
            status_code=422, detail="both runs need per-question results to be comparable"
        )

    deltas = compare_runs(
        numeric_metrics_by_question(results_a), numeric_metrics_by_question(results_b)
    )
    if not deltas:
        raise HTTPException(
            status_code=422,
            detail="runs share no questions with comparable metrics (different datasets?)",
        )

    experiment = Experiment(
        name=req.name,
        config_a=run_a.config or {},
        config_b=run_b.config or {},
        run_a_id=req.run_a_id,
        run_b_id=req.run_b_id,
        deltas=deltas,
    )
    db.add(experiment)
    await db.commit()
    await db.refresh(experiment)
    return experiment


@router.get("/experiments", response_model=list[ExperimentOut])
async def list_experiments(db: AsyncSession = Depends(get_db)) -> list[Experiment]:
    result = await db.execute(select(Experiment).order_by(Experiment.created_at.desc()))
    return list(result.scalars().all())


@router.get("/experiments/{experiment_id}", response_model=ExperimentDetail)
async def get_experiment(experiment_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> dict:
    experiment = await db.get(Experiment, experiment_id)
    if experiment is None:
        raise HTTPException(status_code=404, detail="experiment not found")
    run_a = await db.get(EvalRun, experiment.run_a_id)
    run_b = await db.get(EvalRun, experiment.run_b_id)
    return {
        "id": experiment.id,
        "name": experiment.name,
        "config_a": experiment.config_a,
        "config_b": experiment.config_b,
        "run_a_id": experiment.run_a_id,
        "run_b_id": experiment.run_b_id,
        "deltas": experiment.deltas,
        "created_at": experiment.created_at,
        "run_a_name": run_a.name if run_a else "(deleted)",
        "run_b_name": run_b.name if run_b else "(deleted)",
    }
