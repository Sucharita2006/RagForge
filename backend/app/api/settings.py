from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.session import get_db
from app.models.settings import AppSetting, CalibrationRun
from app.schemas.settings import AbstainThresholdPatch, SettingsOut
from app.trust.abstain import ABSTAIN_THRESHOLD_KEY, get_abstain_threshold

router = APIRouter(tags=["settings"])


@router.get("/settings", response_model=SettingsOut)
async def get_settings_view(db: AsyncSession = Depends(get_db)) -> SettingsOut:
    settings = get_settings()
    threshold = await get_abstain_threshold(db)
    result = await db.execute(
        select(CalibrationRun).order_by(CalibrationRun.created_at.desc()).limit(1)
    )
    calibration_row = result.scalars().first()
    return SettingsOut(
        abstain_threshold=threshold,
        confidence_weights={
            "claim_support": settings.CONFIDENCE_WEIGHT_CLAIM_SUPPORT,
            "retrieval": settings.CONFIDENCE_WEIGHT_RETRIEVAL,
            "sufficiency": settings.CONFIDENCE_WEIGHT_SUFFICIENCY,
        },
        minicheck_support_threshold=settings.MINICHECK_SUPPORT_THRESHOLD,
        calibration_curve=calibration_row.curve if calibration_row else None,
    )


@router.patch("/settings/abstain-threshold", response_model=SettingsOut)
async def patch_abstain_threshold(
    body: AbstainThresholdPatch, db: AsyncSession = Depends(get_db)
) -> SettingsOut:
    if not 0.0 <= body.threshold <= 1.0:
        raise HTTPException(status_code=422, detail="threshold must be between 0 and 1")

    existing = await db.get(AppSetting, ABSTAIN_THRESHOLD_KEY)
    if existing is None:
        db.add(AppSetting(key=ABSTAIN_THRESHOLD_KEY, value={"threshold": body.threshold}))
    else:
        existing.value = {"threshold": body.threshold}
    await db.commit()

    return await get_settings_view(db)
