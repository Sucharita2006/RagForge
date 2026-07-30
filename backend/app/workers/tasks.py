from app.workers.celery_app import celery_app


@celery_app.task(name="ping")
def ping() -> str:
    """Phase 0 smoke-test task; real jobs land phase-by-phase (ingest/finetune/eval/redteam)."""
    return "pong"
