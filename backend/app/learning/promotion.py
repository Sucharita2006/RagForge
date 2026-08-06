from app.evals.experiments import compare_runs

# The metrics a reranker/embedder promotion is judged on. Deliberately
# retrieval-only: a reranker change cannot improve faithfulness except
# through retrieval, so gating on generation metrics would add noise (and a
# dependency on which generation provider happened to run) to the decision.
GATE_METRICS = ("ndcg@10", "hit_rate")


class PromotionRejected(Exception):
    """Raised when a candidate fails the A/B gate. Carries the per-metric
    detail so the caller can explain *why* rather than just refusing."""

    def __init__(self, reason: str, detail: dict) -> None:
        super().__init__(reason)
        self.reason = reason
        self.detail = detail


def evaluate_promotion(
    metrics_active: dict[str, dict[str, float]],
    metrics_candidate: dict[str, dict[str, float]],
) -> dict:
    """SPEC.md §3.5's promotion gate: compare candidate against active on the
    golden set and **promote only if a bootstrap 95% CI excludes 0**.

    Reuses Phase 5's `compare_runs` (paired bootstrap) so the gate and the
    Experiments page can never disagree about what a real improvement is.

    Decision rule, stated explicitly because "improved" is doing real work
    here: promote if at least one gate metric significantly improved **and**
    none significantly regressed. A candidate that trades NDCG for hit-rate
    is not an upgrade, and a CI that merely touches 0 is not evidence.
    """
    comparison = compare_runs(metrics_active, metrics_candidate)
    gate = {m: comparison[m] for m in GATE_METRICS if m in comparison}

    if not gate:
        raise PromotionRejected(
            "no gate metrics in common between the two runs "
            f"(need at least one of {list(GATE_METRICS)})",
            comparison,
        )

    improved = [m for m, r in gate.items() if r["significant"] and r["improved"]]
    regressed = [m for m, r in gate.items() if r["significant"] and not r["improved"]]

    if regressed:
        raise PromotionRejected(
            f"candidate significantly regressed on {regressed}",
            gate,
        )
    if not improved:
        raise PromotionRejected(
            "no gate metric improved with a 95% CI excluding 0 "
            "(the candidate is not measurably better)",
            gate,
        )
    return {"improved_metrics": improved, "gate": gate}
