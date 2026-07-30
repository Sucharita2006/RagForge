from fastapi import APIRouter
from sqlalchemy import text

from app.db.session import engine
from app.schemas.health import HealthResponse, ReadyResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse()


@router.get("/ready", response_model=ReadyResponse)
async def ready() -> ReadyResponse:
    db_ok = False
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False
    return ReadyResponse(status="ok" if db_ok else "degraded", database=db_ok)
