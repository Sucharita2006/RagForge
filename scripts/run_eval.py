"""Deterministic retrieval eval (implementation-plan.md amendment A1):
hit_rate@k, MRR, NDCG@10 against the mini golden set — no LLM judge, so
baseline-v0 has real numbers from Phase 1 day one, and Phase 2+ has
something concrete to beat.

Document-level matching: each golden item names the arXiv id that should be
retrieved; a "hit" is any retrieved chunk belonging to that document.

Usage (stack must be up):
    pip install -r scripts/requirements.txt
    python scripts/run_eval.py [--golden-set path] [--top-k 10] [--output path]
"""

import argparse
import json
import math
import statistics
from pathlib import Path

import httpx

API_BASE = "http://localhost:8000/api"
DEFAULT_GOLDEN_SET = Path(__file__).resolve().parent.parent / "eval-datasets" / "v0" / "mini.jsonl"


def load_golden_set(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def retrieve(client: httpx.Client, question: str, top_k: int) -> list[str | None]:
    resp = client.post("/retrieve", json={"question": question, "top_k": top_k}, timeout=30.0)
    resp.raise_for_status()
    return [c["document_external_id"] for c in resp.json()["candidates"]]


def hit_rate(ranked: list[str | None], expected: str) -> float:
    return 1.0 if expected in ranked else 0.0


def reciprocal_rank(ranked: list[str | None], expected: str) -> float:
    for i, doc in enumerate(ranked, start=1):
        if doc == expected:
            return 1.0 / i
    return 0.0


def ndcg_at_k(ranked: list[str | None], expected: str, k: int) -> float:
    dcg = 0.0
    for i, doc in enumerate(ranked[:k], start=1):
        if doc == expected:
            dcg = 1.0 / math.log2(i + 1)
            break
    idcg = 1.0 / math.log2(2)  # ideal: the single relevant doc at rank 1
    return dcg / idcg


def main() -> dict:
    parser = argparse.ArgumentParser()
    parser.add_argument("--golden-set", type=Path, default=DEFAULT_GOLDEN_SET)
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    golden_set = load_golden_set(args.golden_set)
    answerable = [item for item in golden_set if not item.get("unanswerable")]
    print(f"Loaded {len(golden_set)} golden-set items ({len(answerable)} answerable)")

    hit_rates, rrs, ndcgs = [], [], []
    per_question = []
    with httpx.Client(base_url=API_BASE) as client:
        for item in answerable:
            ranked = retrieve(client, item["question"], args.top_k)
            hr = hit_rate(ranked, item["expected_arxiv_id"])
            rr = reciprocal_rank(ranked, item["expected_arxiv_id"])
            ndcg = ndcg_at_k(ranked, item["expected_arxiv_id"], 10)
            hit_rates.append(hr)
            rrs.append(rr)
            ndcgs.append(ndcg)
            per_question.append(
                {
                    "question": item["question"],
                    "expected_arxiv_id": item["expected_arxiv_id"],
                    "hit_rate": hr,
                    "reciprocal_rank": rr,
                    "ndcg@10": ndcg,
                }
            )

    metrics = {
        f"hit_rate@{args.top_k}": statistics.mean(hit_rates) if hit_rates else 0.0,
        "mrr": statistics.mean(rrs) if rrs else 0.0,
        "ndcg@10": statistics.mean(ndcgs) if ndcgs else 0.0,
        "n_questions": len(hit_rates),
    }
    print(json.dumps(metrics, indent=2))

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps({"metrics": metrics, "per_question": per_question}, indent=2))

    return metrics


if __name__ == "__main__":
    main()
