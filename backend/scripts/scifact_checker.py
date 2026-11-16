"""Tests the answer checker on SciFact's expert-labelled claims.

Every answer sentence /api/query returns is checked against the passage it
cites by MiniCheck (app.trust.minicheck), and a sentence counts as supported
when its probability reaches MINICHECK_SUPPORT_THRESHOLD. Nothing measured
that checker on data it was not tuned for; this does.

SciFact (Wadden et al., 2020) pairs scientific claims with paper abstracts
that experts marked as supporting or contradicting them, and claims with no
evidence cite an abstract that does neither. Each (claim, abstract) pair of
the labelled dev split goes through the production provider and threshold.
A "supported" verdict is right only for SUPPORT pairs.

    docker compose run --rm api python -m scripts.scifact_checker

Writes eval-datasets/benchmarks/scifact-checker.json: the summary plus one
row per pair (ids, label, probability; no SciFact text).
"""

import io
import json
import random
import shutil
import tarfile
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from app.config import get_settings
from app.evals.bootstrap import bootstrap_ci
from app.trust.minicheck import get_minicheck_provider

settings = get_settings()

RELEASE = "https://scifact.s3-us-west-2.amazonaws.com/release/latest/data.tar.gz"
BACKEND = Path(__file__).resolve().parent.parent
DATA = next(
    p for p in (BACKEND / "eval-datasets", BACKEND.parent / "eval-datasets") if (p / "v1").is_dir()
)
SUPPORT, CONTRADICT, NEI = "SUPPORT", "CONTRADICT", "NOT_ENOUGH_INFO"


@dataclass(frozen=True)
class Pair:
    claim_id: int
    doc_id: int
    label: str
    claim: str
    premise: str


def read_release() -> tuple[list[dict], dict[int, dict]]:
    """Labelled dev claims and the abstract corpus, read straight out of the
    cached archive (nothing is extracted to disk)."""
    archive = DATA / "downloads" / "scifact-release.tar.gz"
    if not archive.exists():
        archive.parent.mkdir(parents=True, exist_ok=True)
        print(f"downloading {RELEASE}", flush=True)
        partial = archive.with_suffix(".part")
        with urllib.request.urlopen(RELEASE, timeout=120) as response, partial.open("wb") as out:
            shutil.copyfileobj(response, out)
        partial.rename(archive)

    with tarfile.open(archive, "r:gz") as tar:

        def rows(member: str) -> list[dict]:
            raw = tar.extractfile(member)
            assert raw is not None, f"{member} missing from {archive.name}"
            return [json.loads(line) for line in io.TextIOWrapper(raw, encoding="utf-8") if line]

        claims = rows("data/claims_dev.jsonl")
        corpus = {doc["doc_id"]: doc for doc in rows("data/corpus.jsonl")}
    return claims, corpus


def build_pairs(claims: list[dict], corpus: dict[int, dict]) -> list[Pair]:
    """One pair per (claim, abstract): the evidence label when the abstract
    has rationale sentences, NOT_ENOUGH_INFO for an abstract the claim cites
    without evidence. The premise is the whole abstract, the way a retrieved
    chunk reaches the checker, not the rationale sentences alone."""
    pairs = []
    for claim in claims:
        evidence = claim.get("evidence") or {}
        labelled = {int(doc_id): sets[0]["label"] for doc_id, sets in evidence.items() if sets}
        for doc_id in labelled or claim.get("cited_doc_ids", []):
            doc = corpus.get(int(doc_id))
            if doc is None:
                continue
            pairs.append(
                Pair(
                    claim_id=claim["id"],
                    doc_id=int(doc_id),
                    label=labelled.get(int(doc_id), NEI),
                    claim=claim["claim"],
                    premise=f"{doc['title']}\n{' '.join(doc['abstract'])}",
                )
            )
    return pairs


def auroc(positive: list[float], negative: list[float]) -> float:
    """Probability that a random SUPPORT pair outscores a random other pair
    (Mann-Whitney, ties count half). Threshold-free, unlike accuracy."""
    if not positive or not negative:
        return float("nan")
    wins = sum((p > n) + 0.5 * (p == n) for p in positive for n in negative)
    return wins / (len(positive) * len(negative))


def balanced_accuracy(labels: list[str], judged: list[bool]) -> float:
    hit = [j for label, j in zip(labels, judged, strict=True) if label == SUPPORT]
    rejected = [not j for label, j in zip(labels, judged, strict=True) if label != SUPPORT]
    if not hit or not rejected:
        return float("nan")
    return (sum(hit) / len(hit) + sum(rejected) / len(rejected)) / 2


def bootstrap(
    n: int, statistic: Callable[[list[int]], float], resamples: int = 2000, seed: int = 42
) -> list[float]:
    """95% percentile interval of a statistic over resampled pair indices."""
    rng = random.Random(seed)
    values = sorted(statistic([rng.randrange(n) for _ in range(n)]) for _ in range(resamples))
    return [values[int(0.025 * resamples)], values[min(resamples - 1, int(0.975 * resamples))]]


def summarize(labels: list[str], probs: list[float], threshold: float) -> dict:
    judged = [p >= threshold for p in probs]

    def share(values: list[bool]) -> dict:
        ci = bootstrap_ci([1.0 if v else 0.0 for v in values])
        return {"mean": ci["mean"], "ci95": [ci["ci_low"], ci["ci_high"]], "n": ci["n"]}

    def ba(idx: list[int]) -> float:
        return balanced_accuracy([labels[i] for i in idx], [judged[i] for i in idx])

    def area(idx: list[int]) -> float:
        return auroc(
            [probs[i] for i in idx if labels[i] == SUPPORT],
            [probs[i] for i in idx if labels[i] != SUPPORT],
        )

    everything = list(range(len(labels)))
    return {
        "threshold": threshold,
        "pairs": len(labels),
        "judged_supported_by_label": {
            label: share([j for lab, j in zip(labels, judged, strict=True) if lab == label])
            for label in (SUPPORT, CONTRADICT, NEI)
        },
        "precision_of_supported": share(
            [lab == SUPPORT for lab, j in zip(labels, judged, strict=True) if j]
        ),
        "balanced_accuracy": {"mean": ba(everything), "ci95": bootstrap(len(labels), ba)},
        "auroc": {"mean": area(everything), "ci95": bootstrap(len(labels), area)},
    }


def main() -> None:
    claims, corpus = read_release()
    pairs = build_pairs(claims, corpus)
    print(f"{len(claims)} dev claims -> {len(pairs)} (claim, abstract) pairs", flush=True)

    checker = get_minicheck_provider()
    probs: list[float] = []
    for start in range(0, len(pairs), 16):
        batch = pairs[start : start + 16]
        probs += checker.score(claims=[p.claim for p in batch], docs=[p.premise for p in batch])
        print(f"scored {len(probs)}/{len(pairs)}", flush=True)

    summary = summarize([p.label for p in pairs], probs, settings.MINICHECK_SUPPORT_THRESHOLD) | {
        "checker": checker.model_name,
        "dataset": "SciFact dev, release/latest",
    }
    out = DATA / "benchmarks" / "scifact-checker.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(
            {
                "summary": summary,
                "pairs": [
                    {"claim_id": p.claim_id, "doc_id": p.doc_id, "label": p.label, "prob": prob}
                    for p, prob in zip(pairs, probs, strict=True)
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
