from app.evals.bootstrap import paired_bootstrap_delta_ci

# Metrics where a *lower* value is the improvement, so a negative delta is a
# win. Everything else is assumed higher-is-better.
LOWER_IS_BETTER = frozenset({"unsupported_claim_rate", "latency_ms", "abstained"})


def compare_runs(
    metrics_a: dict[str, dict[str, float]], metrics_b: dict[str, dict[str, float]]
) -> dict:
    """Per-metric paired A/B comparison of two eval runs (SPEC.md §3.9 page 5).

    `metrics_a`/`metrics_b` map question_id -> {metric: value}. Only
    questions present in *both* runs and carrying the metric on both sides
    are compared - an item that failed in one run (Phase 4's per-item
    isolation means runs can legitimately have holes) would otherwise
    silently bias the delta toward whichever run completed it.

    Returns {metric: {delta, ci_low, ci_high, n, significant, improved}}.
    """
    shared_questions = sorted(set(metrics_a) & set(metrics_b))
    metric_names = sorted(
        {m for q in shared_questions for m in metrics_a[q]}
        & {m for q in shared_questions for m in metrics_b[q]}
    )

    comparison: dict[str, dict] = {}
    for metric in metric_names:
        pairs = [
            (float(metrics_a[q][metric]), float(metrics_b[q][metric]))
            for q in shared_questions
            if metric in metrics_a[q] and metric in metrics_b[q]
        ]
        if not pairs:
            continue
        result = paired_bootstrap_delta_ci(pairs)
        lower_better = metric in LOWER_IS_BETTER
        result["improved"] = result["significant"] and (
            result["delta"] < 0 if lower_better else result["delta"] > 0
        )
        result["lower_is_better"] = lower_better
        result["mean_a"] = sum(a for a, _ in pairs) / len(pairs)
        result["mean_b"] = sum(b for _, b in pairs) / len(pairs)
        comparison[metric] = result
    return comparison


def numeric_metrics_by_question(results: list) -> dict[str, dict[str, float]]:
    """Flatten EvalResult rows into question_id -> {metric: float}, coercing
    bools to 1.0/0.0 the same way `aggregate_metrics` does so a comparison
    and a run's own aggregate never disagree on what a metric means."""
    by_question: dict[str, dict[str, float]] = {}
    for row in results:
        values: dict[str, float] = {}
        for key, value in (row.metrics or {}).items():
            if isinstance(value, bool):
                values[key] = 1.0 if value else 0.0
            elif isinstance(value, int | float):
                values[key] = float(value)
        by_question[row.question_id] = values
    return by_question
