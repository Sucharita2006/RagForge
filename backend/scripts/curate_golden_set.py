"""Golden set v1 curation pass (SPEC.md §8.3 "human-curate").

Reads the raw generated output (scripts/generate_golden_set.py) and:
1. Dedupes near-identical items via word-overlap (Jaccard) similarity -
   found live: unanswerable-item generation converged heavily on one
   topic ("IoT sensor data") at GEN_TEMPERATURE=0.1, since a title-list
   shuffle alone wasn't enough perturbation to escape the model's
   strongest completion (DECISIONS.md 2026-08-01).
2. Backfills any resulting shortfall with a regeneration pass that
   explicitly lists already-used topics to avoid, one item at a time so
   each new item also avoids every topic generated earlier in the
   backfill itself.
3. Writes eval-datasets/v1/full.jsonl plus derived calibration.jsonl (40
   items) and ci_split.jsonl (30 items) subsets (SPEC.md §8.3 split).

Run inside the container: docker compose exec api python scripts/curate_golden_set.py
"""

import asyncio
import json
import random
import re
from pathlib import Path

from sqlalchemy import select

from app.db.session import async_session_maker
from app.models.documents import Document
from app.models.evals import EvalDataset
from app.providers.llm.ollama import OllamaProvider
from scripts.generate_golden_set import UNANSWERABLE_PROMPT, _parse_question_answer

RAW_PATH = Path("/app/data/eval-datasets-v1-full.raw.jsonl")
OUTPUT_DIR = Path("/app/eval-datasets/v1")
TARGET_COUNTS = {"single_hop": 55, "multi_hop": 30, "unanswerable": 25, "adversarial": 10}
DEDUPE_THRESHOLD = 0.55

STOPWORDS = {
    "the", "a", "an", "of", "in", "on", "to", "and", "how", "does", "do", "is",
    "are", "for", "with", "this", "that", "from", "as", "by", "its", "it", "or",
    "be", "used", "affect", "compare", "differ", "between", "both",
}  # fmt: skip


def _word_set(question: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+", question.lower())
    return {w for w in words if w not in STOPWORDS}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def dedupe(items: list[dict]) -> tuple[list[dict], list[dict]]:
    kept: list[dict] = []
    kept_word_sets: list[set[str]] = []
    dropped: list[dict] = []
    for item in items:
        ws = _word_set(item["question"])
        if any(_jaccard(ws, k) >= DEDUPE_THRESHOLD for k in kept_word_sets):
            dropped.append(item)
            continue
        kept.append(item)
        kept_word_sets.append(ws)
    return kept, dropped


async def backfill_unanswerable(
    llm: OllamaProvider, existing_questions: list[str], n_needed: int, titles: list[str]
) -> list[dict]:
    avoid_list = list(existing_questions)
    new_items: list[dict] = []
    for i in range(n_needed):
        shuffled = titles[:]
        random.shuffle(shuffled)
        avoid_block = "\n".join(f"- {q}" for q in avoid_list) or "(none yet)"
        prompt = (
            UNANSWERABLE_PROMPT.format(titles="\n".join(f"- {t}" for t in shuffled))
            + "\n\nDo NOT ask about any of these topics, which are already used:\n"
            + avoid_block
            + "\n\nThe new question must be about a clearly different topic than all of the above."
        )
        gen = await llm.generate("You generate evaluation questions.", prompt)
        question, _ = _parse_question_answer(gen["text"])
        avoid_list.append(question)
        new_items.append(
            {
                "id": f"ua_backfill_{i:03d}",
                "type": "unanswerable",
                "question": question,
                "reference_answer": None,
                "expected_arxiv_ids": [],
                "unanswerable": True,
            }
        )
        print(f"  backfill [{i + 1}/{n_needed}] ({gen['latency_ms']}ms) {question[:80]}")
    return new_items


async def main() -> None:
    raw_items = [json.loads(line) for line in RAW_PATH.read_text().splitlines() if line.strip()]
    by_type: dict[str, list[dict]] = {}
    for item in raw_items:
        by_type.setdefault(item["type"], []).append(item)

    final_items: list[dict] = []
    for item_type, items in by_type.items():
        kept, dropped = dedupe(items)
        print(
            f"{item_type}: kept {len(kept)}/{len(items)} ({len(dropped)} near-duplicates dropped)"
        )
        final_items.extend(kept)

    unanswerable_count = sum(1 for i in final_items if i["type"] == "unanswerable")
    shortfall = TARGET_COUNTS["unanswerable"] - unanswerable_count
    if shortfall > 0:
        print(f"\nBackfilling {shortfall} unanswerable items to reach target...")
        llm = OllamaProvider()
        # titles come from documents.py at runtime in generate_golden_set.py;
        # here we only have the raw jsonl, so derive a topic-avoidance list
        # purely from already-kept unanswerable questions (titles aren't
        # needed for novelty - only for grounding the prompt's corpus context)
        existing_questions = [i["question"] for i in final_items if i["type"] == "unanswerable"]

        async with async_session_maker() as db:
            result = await db.execute(select(Document.title).where(Document.title.is_not(None)))
            titles = [t for (t,) in result.all()]

        new_items = await backfill_unanswerable(llm, existing_questions, shortfall, titles)
        final_items.extend(new_items)

    random.shuffle(final_items)
    for idx, item in enumerate(final_items, start=1):
        item["id"] = f"{item['type'][:2]}_{idx:03d}"

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    full_path = OUTPUT_DIR / "full.jsonl"
    with full_path.open("w") as f:
        for item in final_items:
            f.write(json.dumps(item) + "\n")
    print(f"\nWrote {len(final_items)} items to {full_path}")

    composition = {t: sum(1 for i in final_items if i["type"] == t) for t in TARGET_COUNTS}
    print(f"Final composition: {composition}")

    # calibration.jsonl: every unanswerable/adversarial item (calibration
    # cares most about the abstain/answer boundary) plus a spread of
    # answerable items, capped at 40 (SPEC.md B5 split)
    priority_types = ("unanswerable", "adversarial")
    priority_items = [i for i in final_items if i["type"] in priority_types]
    answerable = [i for i in final_items if i["type"] in ("single_hop", "multi_hop")]
    calibration = priority_items + answerable[: max(0, 40 - len(priority_items))]
    (OUTPUT_DIR / "calibration.jsonl").write_text(
        "\n".join(json.dumps(i) for i in calibration) + "\n"
    )
    print(f"Wrote {len(calibration)} items to calibration.jsonl")

    # ci_split.jsonl: a fast, representative 30-item subset for local/manual
    # quick retrieval-only checks against the real corpus (not the same as
    # the GitHub Actions fixture-corpus smoke test, see DECISIONS.md)
    ci_split = final_items[:30]
    (OUTPUT_DIR / "ci_split.jsonl").write_text("\n".join(json.dumps(i) for i in ci_split) + "\n")
    print(f"Wrote {len(ci_split)} items to ci_split.jsonl")

    async with async_session_maker() as db:
        existing = await db.execute(select(EvalDataset).where(EvalDataset.version == "v1"))
        row = existing.scalar_one_or_none()
        if row is None:
            row = EvalDataset(version="v1", path=str(full_path), size=len(final_items))
            db.add(row)
        else:
            row.size = len(final_items)
        row.composition = composition
        await db.commit()
    print("Registered eval-dataset v1 in eval_datasets.")


if __name__ == "__main__":
    asyncio.run(main())
