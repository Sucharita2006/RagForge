"""Abstain-threshold calibration job (SPEC.md §8.5): runs the full
retrieve -> generate -> verify pipeline over eval-datasets/v1/calibration.jsonl,
sweeps candidate thresholds against the resulting confidence scores, and
persists the lowest threshold meeting >=TARGET_PRECISION answered-precision
as the live ABSTAIN_THRESHOLD override (app_settings table).

Run inside the container: docker compose exec api python scripts/calibrate_abstain_threshold.py
"""

import asyncio
import uuid
from pathlib import Path

from app.db.session import async_session_maker
from app.models.settings import AppSetting, CalibrationRun
from app.providers.embeddings.bge_small import get_embedding_provider
from app.providers.llm.ollama import OllamaProvider
from app.trust.abstain import ABSTAIN_THRESHOLD_KEY
from app.trust.calibration import (
    choose_threshold,
    compute_calibration_confidences,
    load_calibration_set,
    sweep_thresholds,
)
from app.trust.minicheck import get_minicheck_provider

DATASET_PATH = Path("/app/eval-datasets/v1/calibration.jsonl")
TARGET_PRECISION = 0.90


async def main() -> None:
    items = load_calibration_set(DATASET_PATH)
    print(f"Loaded {len(items)} calibration items from {DATASET_PATH}")

    embedder = get_embedding_provider()
    llm = OllamaProvider(timeout=1200.0)  # background job, not an interactive request
    minicheck = get_minicheck_provider()

    async with async_session_maker() as db:
        scored = await compute_calibration_confidences(db, items, embedder, llm, minicheck)

    for item, confidence in scored:
        print(
            f"  {item.id} ({item.type}, unanswerable={item.unanswerable}): "
            f"confidence={confidence:.3f}"
        )

    curve = sweep_thresholds(scored)
    chosen = choose_threshold(curve, TARGET_PRECISION)
    print(f"\nChosen threshold: {chosen:.3f} (target precision >= {TARGET_PRECISION})")

    async with async_session_maker() as db:
        db.add(
            CalibrationRun(
                id=uuid.uuid4(),
                dataset_path=str(DATASET_PATH),
                curve=curve,
                chosen_threshold=chosen,
                target_precision=TARGET_PRECISION,
            )
        )
        existing = await db.get(AppSetting, ABSTAIN_THRESHOLD_KEY)
        if existing is None:
            db.add(AppSetting(key=ABSTAIN_THRESHOLD_KEY, value={"threshold": chosen}))
        else:
            existing.value = {"threshold": chosen}
        await db.commit()

    print("Persisted calibration run and updated the live abstain_threshold setting.")


if __name__ == "__main__":
    asyncio.run(main())
