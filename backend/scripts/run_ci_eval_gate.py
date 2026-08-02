"""Fast, per-PR retrieval smoke gate (SPEC.md §8.7 evals.yml, C3: hard-fail
only on deterministic retrieval metrics).

Runs against the tiny CI fixture corpus (scripts/generate_ci_fixtures.py),
not the real golden-set-v1 + baselines/baseline.json regression rule
(SPEC.md §7.2) - re-ingesting/embedding/indexing the real 40-document
corpus on every PR isn't feasible on a free GitHub-hosted runner
(DECISIONS.md 2026-08-01). This is a scoped smoke test: every answerable
fixture question must retrieve its one obviously-correct document at
rank 1 - a real regression in the retrieval pipeline fails it, but it
cannot catch subtler quality regressions the way a full run against the
real corpus (via POST /api/eval/run) would.
"""

import json
import sys
from pathlib import Path

import httpx

API_BASE = "http://localhost:8000/api"
# scripts/ -> /app inside the container, where eval-datasets/ is mounted
# directly (docker-compose.yml); on the host this is backend/scripts/../../eval-datasets
GOLDEN_PATH = (
    Path(__file__).resolve().parent.parent / "eval-datasets" / "ci-fixture" / "golden.jsonl"
)


def main() -> None:
    items = [json.loads(line) for line in GOLDEN_PATH.read_text().splitlines() if line.strip()]
    failures = []

    with httpx.Client(base_url=API_BASE) as client:
        # first request after a fresh container start pays for cold-loading
        # the embedding + reranker models - absorb that outside the loop
        # below so a slow-but-healthy first call doesn't read as a failure.
        client.post("/retrieve", json={"question": "warmup", "top_k": 1}, timeout=120.0)

        for item in items:
            resp = client.post(
                "/retrieve", json={"question": item["question"], "top_k": 5}, timeout=30.0
            )
            resp.raise_for_status()
            candidates = resp.json()["candidates"]
            ranked_ids = [c["document_external_id"] for c in candidates]

            if item["unanswerable"]:
                continue  # no positive-match assertion for unanswerable items

            expected = set(item["expected_arxiv_ids"])
            if not ranked_ids or ranked_ids[0] not in expected:
                failures.append(
                    {"question_id": item["id"], "expected": list(expected), "got": ranked_ids[:3]}
                )

    if failures:
        print("Retrieval smoke gate FAILED:", file=sys.stderr)
        for f in failures:
            print(f"  {f}", file=sys.stderr)
        sys.exit(1)

    print(f"Retrieval smoke gate passed: {len(items)} fixture questions checked.")


if __name__ == "__main__":
    main()
