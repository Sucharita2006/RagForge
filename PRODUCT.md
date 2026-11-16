# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Project reviewers: hiring managers and engineers who open the running demo for a few minutes to judge the engineering behind it (confirmed 2026-11-15). They are technical, short on time, and have seen many chat-with-your-documents demos.

The engineer who runs the system (debugging retrieval, running evals, comparing experiments) also uses every page, but is not the audience the interface is designed for first.

## Product Purpose

ragforge is a self-hosted Retrieval-Augmented Generation platform: ingest documents, ask questions, get answers grounded in the corpus with per-sentence citations. Around that sit an evaluation harness, CI regression gates, tracing and analytics, and a feedback loop that fine-tunes and gates new rerankers.

The interface succeeds when a reviewer, in one question, sees that answers are checked.

## Positioning

Every sentence of an answer is tested against the passage it cites (MiniCheck entailment), the answer carries a confidence built from claim support, retrieval strength and citation coverage, and below a calibrated threshold the system declines to answer and shows the sources it found instead.

The one thing the interface must make unmistakable: answers are checked (confirmed 2026-11-15).

## Operating Context

- Runs locally with `docker compose`: FastAPI, PostgreSQL + pgvector, Redis, Celery, with Ollama on the host for generation. The frontend is a Next.js App Router app that calls the API from the browser (`NEXT_PUBLIC_API_URL`).
- Reviewers usually arrive from the README or a résumé link.
- A query is slow on the documented CPU profile: about 250 s warm end to end (generation ~158 s, claim verification ~86 s, retrieval ~8 s). Waiting is part of using the product.

## Capabilities and Constraints

Eight pages, grouped by job in the navigation:

- **Query** (`/`): ask a question; see claims with verdict and support probability, the passages they cite, confidence against the threshold, abstention with sources, model and latency; rate the answer and optionally submit a correction.
- Inspect
  - **Candidates** (`/candidates`): one question's candidates with dense, BM25, fused and rerank scores.
  - **Timeline** (`/timeline`): recent traces and one trace's span waterfall, latency, cost and outcome.
- Measure
  - **Golden set** (`/golden-set`): evaluation runs with aggregate metrics, intervals, per-question results and judge notes.
  - **A/B** (`/ab`): paired comparison of two runs, per-metric difference with 95% interval and a verdict.
  - **Metrics** (`/metrics`): latency percentiles, cache and abstention rates and cost over a time window, by pipeline stage.
- Improve
  - **Feedback loop** (`/feedback-loop`): model registry, promotion gate with its per-metric interval table, reranker fine-tuning, failure clusters, feedback received.
  - **Trust settings** (`/trust-settings`): abstain threshold (live-mutable), confidence weights, calibration curve.

Constraints: Next.js 16, React 19, Tailwind CSS 3, no component library; API shapes are fixed by the backend.

Undecided: no deployment target or public demo URL is confirmed.

## Brand Commitments

- The name is written lowercase, `ragforge`, in the interface and the README title.
- No logo or other brand assets exist.
- Page names, routes and their grouping (Query; Inspect, Measure, Improve) and the magenta identity colour were chosen by the owner (2026-11-16).

## Evidence on Hand

- Measured results in `README.md`, `baselines/*.json` and `DECISIONS.md`, including targets that were missed (unsupported-claim rate 0.398 against ≤0.05; ECE 0.176 against ≤0.10) and a promotion gate that refused a real candidate model.
- Public benchmark results in `eval-datasets/public-results/`.
- No testimonials, customers, pricing, press or logo exist. Do not invent them.

## Product Principles

1. Show the check, not the claim: a verdict sits next to the sentence it judges.
2. A refusal is a result. Abstaining, and a gate that says no, are shown as outcomes, not errors.
3. Report what was measured, including the misses.
4. A reviewer reaches proof in one interaction.
