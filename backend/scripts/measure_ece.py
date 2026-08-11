"""Measure confidence calibration (ECE) against SPEC.md §7.2's <= 0.10 target,
and print the reliability diagram it's computed from.

ECE is over *answered* items only - see app/trust/ece.py for why abstentions
are excluded rather than counted as low-confidence successes.

Correctness label: the judge's `answer_correctness` >= CORRECT_THRESHOLD.
That is the only per-item ground truth available for answered items; the
alternative (`abstention_correct`) measures the answer/abstain decision, not
whether the produced answer was right, which is what confidence claims to predict.

Run:
  docker compose exec -e PYTHONPATH=/app api python scripts/measure_ece.py [run_name]
"""

import asyncio
import sys

from sqlalchemy import select

from app.db.session import async_session_maker
from app.models.evals import EvalResult, EvalRun
from app.trust.ece import (
    expected_calibration_error,
    maximum_calibration_error,
    reliability_bins,
)

CORRECT_THRESHOLD = 0.5
TARGET_ECE = 0.10
DEFAULT_RUN = "phase4-trust-baseline-v3"


async def main() -> None:
    run_name = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_RUN

    async with async_session_maker() as db:
        run = (await db.execute(select(EvalRun).where(EvalRun.name == run_name))).scalars().first()
        if run is None:
            print(f"no eval run named {run_name!r}")
            return
        results = list(
            (await db.execute(select(EvalResult).where(EvalResult.run_id == run.id)))
            .scalars()
            .all()
        )

    pairs: list[tuple[float, bool]] = []
    skipped_abstained = 0
    skipped_unjudged = 0
    for r in results:
        m = r.metrics or {}
        if "confidence" not in m:
            continue
        if m.get("abstained") is True:
            skipped_abstained += 1
            continue
        if m.get("answer_correctness") is None:
            skipped_unjudged += 1
            continue
        pairs.append((float(m["confidence"]), float(m["answer_correctness"]) >= CORRECT_THRESHOLD))

    print(f"run          : {run_name}")
    print(f"answered+judged items used : {len(pairs)}")
    print(f"  skipped (abstained)      : {skipped_abstained}")
    print(f"  skipped (not judged)     : {skipped_unjudged}")

    if not pairs:
        print("\nNo (confidence, correctness) pairs available - cannot measure ECE.")
        return

    ece = expected_calibration_error(pairs)
    mce = maximum_calibration_error(pairs)

    print("\nReliability diagram (equal-width bins, empty bins omitted):")
    print(f"  {'bin':>12} {'n':>3} {'mean_conf':>10} {'accuracy':>9} {'gap':>7}")
    for b in reliability_bins(pairs):
        label = f"[{b['bin_low']:.1f},{b['bin_high']:.1f})"
        print(
            f"  {label:>12} {b['count']:>3} {b['mean_confidence']:>10.3f} "
            f"{b['accuracy']:>9.3f} {b['gap']:>7.3f}"
        )

    verdict = "PASS" if ece <= TARGET_ECE else "FAIL"
    print(f"\nECE = {ece:.4f}   (target <= {TARGET_ECE})   -> {verdict}")
    print(f"MCE = {mce:.4f}   (worst single bin)")

    mean_conf = sum(c for c, _ in pairs) / len(pairs)
    accuracy = sum(1 for _, ok in pairs if ok) / len(pairs)
    direction = "over" if mean_conf > accuracy else "under"
    print(
        f"\nOverall: mean confidence {mean_conf:.3f} vs accuracy {accuracy:.3f} "
        f"-> {direction}-confident by {abs(mean_conf - accuracy):.3f}"
    )


if __name__ == "__main__":
    asyncio.run(main())
