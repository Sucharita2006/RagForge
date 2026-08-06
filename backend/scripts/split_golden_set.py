"""Deterministic train/held-out split of golden set v1 (Phase 6).

Why this exists: Phase 6 mines reranker training pairs *from* the golden set
and then A/B-evaluates the fine-tuned model. Doing both on the same items is
train/test contamination - the candidate would be scored on questions it was
trained on, and any "improvement" would measure memorization rather than
generalization. The promotion gate would then be rigorous in form and
worthless in substance.

Split is by `id` hash, so it is stable across re-runs and independent of file
order: re-mining or re-shuffling never silently moves an item across the
boundary and leaks it.

Run:
  docker compose exec -e PYTHONPATH=/app api python scripts/split_golden_set.py
"""

import hashlib
import json
from pathlib import Path

GOLDEN_DIR = Path("/app/eval-datasets/v1")
SOURCE = GOLDEN_DIR / "full.jsonl"
TRAIN_OUT = GOLDEN_DIR / "train.jsonl"
HELDOUT_OUT = GOLDEN_DIR / "heldout.jsonl"

HELDOUT_FRACTION = 0.4


def is_heldout(item_id: str) -> bool:
    """Stable hash-based assignment - not random.shuffle with a seed, because
    that depends on input ordering, which a re-mine could change."""
    digest = hashlib.sha256(item_id.encode()).hexdigest()
    return (int(digest[:8], 16) % 100) < (HELDOUT_FRACTION * 100)


def main() -> None:
    items = [json.loads(line) for line in SOURCE.read_text().splitlines() if line.strip()]
    train = [i for i in items if not is_heldout(i["id"])]
    heldout = [i for i in items if is_heldout(i["id"])]

    TRAIN_OUT.write_text("".join(json.dumps(i) + "\n" for i in train))
    HELDOUT_OUT.write_text("".join(json.dumps(i) + "\n" for i in heldout))

    # Also emit each side as its own versioned dataset folder, because
    # POST /api/eval/run resolves a dataset_version to `{version}/full.jsonl`
    # (SPEC.md §8.3's "version the folder" convention). Without this the
    # gate could only ever be run against the contaminated full set.
    for version, rows in (("v1-train", train), ("v1-heldout", heldout)):
        folder = GOLDEN_DIR.parent / version
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "full.jsonl").write_text("".join(json.dumps(i) + "\n" for i in rows))
        print(f"           also wrote {folder / 'full.jsonl'} (dataset_version={version!r})")

    def answerable(rows: list) -> int:
        return sum(1 for r in rows if r.get("expected_arxiv_ids"))

    print(f"source   : {len(items):3d} items ({answerable(items)} answerable)")
    print(f"train    : {len(train):3d} items ({answerable(train)} answerable) -> {TRAIN_OUT}")
    print(f"held-out : {len(heldout):3d} items ({answerable(heldout)} answerable) -> {HELDOUT_OUT}")

    overlap = {i["id"] for i in train} & {i["id"] for i in heldout}
    assert not overlap, f"split leaked {len(overlap)} items across both sides"
    print("\nNo overlap between splits - safe to train on train.jsonl and gate on heldout.jsonl")


if __name__ == "__main__":
    main()
