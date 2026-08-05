from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.settings import AppSetting

ABSTAIN_THRESHOLD_KEY = "abstain_threshold"


def should_abstain(confidence: float, threshold: float) -> bool:
    return confidence < threshold


async def get_abstain_threshold(db: AsyncSession) -> float:
    """The live threshold PATCH /settings/abstain-threshold can override
    (SPEC.md §3.3/§8.5), falling back to config.py's static default until a
    calibration run or a manual PATCH ever sets one."""
    setting = await db.get(AppSetting, ABSTAIN_THRESHOLD_KEY)
    if setting is not None:
        return float(setting.value["threshold"])
    return get_settings().ABSTAIN_THRESHOLD
