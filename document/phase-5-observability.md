# Phase 5 — Observability + Experiments

**Status:** complete (both exit criteria met)
**Date:** 2026-08-06
**Spec reference:** `SPEC.md` §10 Phase 5, §3.8, §3.9 pages 5–7
**Acceptance criteria:** two configs can be compared with significance, and every query has a full waterfall.

## Goal

Make the pipeline's behaviour inspectable rather than inferred. Every query should leave a complete, queryable span tree (what ran, how long, what it cost, what it retrieved); the aggregate behaviour should be visible as a dashboard; and two configurations should be comparable with a statistical claim rather than an eyeballed diff of two numbers.

## What was built

- **Span persistence** (`app/observability/exporter.py`): a custom OTel `SpanExporter` writing every span to Postgres via `BatchSpanProcessor`. Runs on its own **synchronous** engine (psycopg) rather than the app's asyncpg one — the exporter contract is sync-and-off-thread, so bridging into the async engine would reproduce the `MissingGreenlet` class of bug from Phase 4. Lazily initialized, kill-switched by `SPAN_EXPORT_ENABLED`, and fail-open: a failed export is logged and dropped, never retried into the request path.
- **Full span coverage**: added the missing `RERANKER` span (`app/retrieval/pipeline.py`) with model, input-doc count and the top-k document ids/scores, so the retrieval stage is no longer a black box between fusion and generation. Existing spans enriched with token counts, computed cost, and trust attributes (claim count, unsupported count).
- **Cost model** (`app/observability/cost.py` + config price table): per-span USD cost from input/output tokens. Self-hosted models are priced at a genuine `0.0` rather than left unpriced, so a `$0` total reads as "self-hosted", not "unmeasured".
- **Traces API + page** (`GET /api/traces`, `GET /api/traces/{trace_id}`): a list rolled up to one row per trace (driven off the root `CHAIN` span, which already carries end-to-end latency and query-level flags), and a detail view rendering a proportional waterfall plus every span's full attribute table.
- **Analytics API + page** (`GET /api/analytics/summary`): p50/p95/p99 latency, cache-hit rate, abstention rate, mean confidence, total and per-query cost, a bucketed time series, and a per-span-kind latency breakdown answering "which stage dominates p95".
- **Experiments API + page** (`POST/GET /api/experiments`): paired-bootstrap A/B comparison of two eval runs. Each metric reports Δ, a 95% CI, n, and a verdict — where **significant** means the CI excludes zero (SPEC.md §3.5's promotion-gate rule) and **improved** additionally accounts for direction, since `unsupported_claim_rate` and `latency_ms` are lower-is-better.
- **Online monitor** (`app/observability/monitor.py` + `run_online_monitor` Celery task): samples recent non-abstained answers, judge-scores them for faithfulness against their *reconstructed* source context, emits the result as an `EVALUATOR` span (so the time series and the trace viewer read the same store), and logs an alert if the mean drops more than the configured points vs the prior 7-day window.
- **Tests**: 21 new unit tests (90 total) covering percentile edge cases, cost arithmetic, paired-vs-unpaired bootstrap behaviour, direction handling, and the shared-questions-only rule.

## What changed from the original design (and why)

Full rationale in `DECISIONS.md` (2026-08-06):

1. **The span exporter got its own sync engine.** Not a workaround — the OTel exporter contract is synchronous and runs on a background thread, so this is the correct shape rather than a compromise.
2. **A/B comparison uses a paired bootstrap**, added alongside Phase 3's unpaired `bootstrap_delta_ci`. Every experiment here compares two configs over the same golden set, so pairing cancels per-question difficulty and reaches significance on far fewer items. There's a test asserting the paired CI is genuinely tighter on correlated data, not just that the function runs.
3. **Comparisons intersect on questions present in both runs**, because Phase 4's per-item failure isolation means runs legitimately have holes and averaging over different question sets would bias the delta.
4. **Nearest-rank percentiles over interpolated ones**, so a reported p95 corresponds to a real request that can be clicked through to its trace.
5. **A bug caught in my own code before shipping**: the online monitor initially judged faithfulness with an empty context, which would have produced a confident-looking metric measuring nothing. Fixed to rebuild context from the cited chunk ids, and to skip unscorable answers rather than record a misleading `0.0`.

## Verification (measured, this session)

**Exit criterion 1 — "two configs can be compared with significance": MET.**

Compared the Phase 3 baseline run (Ollama generation) against the Phase 4 trust run (OpenRouter generation) — two genuinely different configs over the same golden set v1. Returned in 0.25s:

```
metric               Δ            95% CI                  verdict
-------------------------------------------------------------------------------
latency_ms           -120,354 ms  [-157713, -83410]       significant, IMPROVED
context_precision    -0.179       [-0.294, -0.076]        significant, REGRESSED
ndcg@10               0.000       [ 0.000,  0.000]        unchanged (n=81)
hit_rate              0.000       [ 0.000,  0.000]        unchanged (n=81)
reciprocal_rank       0.000       [ 0.000,  0.000]        unchanged (n=81)
faithfulness         +0.053       [-0.138, +0.250]        not significant (n=17)
answer_correctness   +0.141       [-0.035, +0.338]        not significant (n=17)
context_recall       +0.115       [-0.035, +0.288]        not significant (n=17)
abstention_correct   +0.031       [ 0.000, +0.094]        not significant (n=32)
```

Four things worth noting, because they're what separates a working comparison tool from one that merely runs:
- It found a **real win** (5x faster generation) and a **real regression** (context precision) in the same comparison, rather than summarizing to a single verdict.
- The three retrieval metrics came back at **exactly 0.000 with zero-width CIs** — correct, since both runs used an identical retrieval pipeline over an identical corpus. A comparison tool that reported noise here would be broken.
- It **declined to claim** faithfulness/answer_correctness/context_recall as improvements despite all three having positive deltas, because their intervals straddle zero.
- `latency_ms` and `context_precision` are both negative deltas, but only the first is marked `improved` — direction handling works.

**Exit criterion 2 — "every query has a full waterfall": MET.**

A live `/api/query` (HTTP 200, 264.9s) produced a complete, correctly-parented span tree, retrieved via `GET /api/traces/{trace_id}`:

```
kind        name             latency_ms   attributes
------------------------------------------------------
CHAIN       query               264,880   4    (root)
EMBEDDING   embed_query              89   0
RETRIEVER   retrieve             14,643   1
RERANKER    rerank                6,515   19
LLM         generate            157,664   4
EVALUATOR   verify_claims        85,849   4
```

The RERANKER span's 19 attributes are model name, input-document count, top_k, and the top-8 document ids with their rerank scores. `GET /api/traces` correctly rolls this up to one row (`span_count: 6`, question text, `cache_hit: false`, `abstained: false`, `cost_usd: 0.0`).

`GET /api/analytics/summary` over the same window returns the per-stage breakdown that makes the dashboard actionable — LLM (157.7s) and EVALUATOR (85.8s) together account for ~92% of end-to-end latency, with retrieval+rerank at 21.2s and embedding negligible at 89ms. Cost reads `$0.0` because generation is self-hosted, which the price table encodes explicitly rather than leaving unpriced.

Engineering verification: `ruff check` / `ruff format --check` / `mypy app` clean (92 source files); `pytest tests/unit` 90 passed (21 new this phase); frontend `eslint` / `tsc --noEmit` / `next build` clean across 8 routes.

## Key decisions this phase

- **Telemetry is fail-open.** Span export failures are logged and dropped; the observability layer must never be able to take down the pipeline it observes.
- **`significant` is defined once, in the bootstrap helper** — so the Experiments page and Phase 6's model-promotion gate cannot drift apart on what "a real improvement" means.
- **Self-hosted cost is `0.0`, not null.** Explicitly priced so a zero total is a measurement, not a gap.

## What's next

**Phase 6 — Learning flywheel**: feedback capture, hard-negative mining, synthetic training pairs, embedder + reranker fine-tuning, a model registry, and a promotion gate that reuses this phase's significance rule — a candidate model only ships if its ΔNDCG CI excludes zero.
