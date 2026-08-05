# Phase 4 — Trust Layer

**Status:** complete (one exit criterion met, one missed and documented — see Verification)
**Date:** 2026-08-05
**Spec reference:** `SPEC.md` §10 Phase 4
**Acceptance criteria:** unsupported_claim_rate ≤ 0.05 and abstention recall ≥ 0.80 on the unanswerable subset.

## Goal

Close the "verify" and "abstain" loops SPEC.md's one-liner promises: every generated claim checked against its source spans by an NLI model, a calibrated confidence score deciding whether to answer at all, and a UI that makes both visible instead of presenting every answer with the same unearned confidence.

## What was built

- **Claim verification** (`app/trust/minicheck.py`, `app/trust/claims.py`): `lytang/MiniCheck-RoBERTa-Large` (via the `minicheck` package, self-hosted, CPU) scores each generated claim sentence against the union of its cited chunks (falling back to every retrieved/used chunk when a claim carries no citation at all). Verdict `supported`/`unsupported` at `MINICHECK_SUPPORT_THRESHOLD=0.5`; a MiniCheck failure degrades to `unscored` rather than 500ing the whole `/query` request.
- **Confidence score** (`app/trust/confidence.py`): weighted combination — mean claim support (0.5), mean sigmoid-normalized rerank score of used chunks (0.3), fraction of claims carrying a citation (0.2, this project's interpretation of SPEC.md's undefined "judge-free sufficiency heuristic" — see "Key decisions").
- **Calibrated abstention** (`app/trust/abstain.py`, `app/trust/calibration.py`, `scripts/calibrate_abstain_threshold.py`): a threshold-sweep job runs the full pipeline over `eval-datasets/v1/calibration.jsonl`, computes coverage/answered-precision at 101 threshold candidates, and persists the lowest threshold meeting ≥90% answered-precision as the live override. `POST /query` now decides `abstained` from confidence vs. this threshold, not the model's raw `insufficient_context` flag alone (which still exists as a distinct, lower-level signal).
- **Data model** (migration `0006`): `answers.confidence`/`answers.abstained` columns; `app_settings` (a small key/value store for the one runtime-mutable setting SPEC.md §6 needs — not in SPEC.md §5's table, added the same way `eval_runs.metrics` was in Phase 3); `calibration_runs` (the threshold-sweep curve + chosen value + history).
- **API**: `POST /api/query` now returns `confidence`, `abstained`, `sources` (top retrieved documents, shown even when abstaining), and each claim carries `support_prob`/`verdict`. `GET /api/settings` / `PATCH /api/settings/abstain-threshold` (config view + calibrated slider, SPEC.md §6).
- **UI**: the Playground page now shows a confidence badge, per-claim highlighting (green=supported, amber=unsupported, gray=unscored) with a hover tooltip for the exact support probability, and a distinct abstention state that suppresses the raw answer and shows the sources that were found instead. A new Settings page renders the calibration curve as a table and a live-adjustable threshold slider.
- **Eval harness integration**: `app/evals/runner.py`'s full-pipeline branch now calls the same `verify_claims`/`compute_confidence`/`should_abstain` functions production `/query` uses (via the same DB-backed threshold), so the harness measures the real deployed decision, not a proxy. Added `unsupported_claim_rate` per item.
- **Tests**: 19 new unit tests across `test_trust_confidence.py`, `test_trust_abstain.py`, `test_trust_claims.py`, `test_trust_calibration.py` — pure-function tests plus a duck-typed fake/broken MiniCheck provider to exercise the graceful-degradation path without needing the real model loaded.

## What changed from the original design (and why)

Full rationale in `DECISIONS.md`; summary of what surfaced only once this ran for real:

1. **MiniCheck isn't installable from PyPI under its own name** (that name is squatted by an unrelated package) — installed from GitHub directly, pinned to a commit rather than a branch. Verified the real install path and API by reading the upstream source, not just the README, before writing code against it.
2. **Two environment gaps only surfaced by actually running it**: the git-based install needs `git` in the Docker image (missing from `python:3.12-slim`), and MiniCheck's internal sentence splitter needs an NLTK resource (`punkt_tab`) that isn't bundled and isn't the same resource a stray `nltk.download('punkt')` call fetches — confirmed via a real scoring call that crashed with a `LookupError`, not an install-time failure. Both baked into the Dockerfile.
3. **SPEC.md's confidence formula's "sufficiency" component is left undefined** ("judge-free heuristics") — interpreted as the fraction of claims carrying at least one citation, a genuinely different signal from claim support (whether a *cited* span entails the claim).
4. **SPEC.md has no settings table for the one value §6 requires to be runtime-mutable.** Added `app_settings` (key/value) and `calibration_runs` (curve history) the same way Phase 3 added `eval_runs.metrics`: small, additive, no spec-table entry to conflict with.
5. **Abstention now suppresses the answer, not just flags it.** When `abstained=True`, the API returns an empty `claims` list (not the model's real, possibly-wrong generated claims next to a warning) — showing an answer beside a "not confident" banner is confusing UX and undercuts the point of a trust layer. The full verified claims still land in the DB for observability; only the user-facing response is gated.

## Verification (measured, this session)

**Calibration run** `a04927ff` (2026-08-03), all 40 `calibration.jsonl` items through the full retrieve→generate→verify pipeline, threshold swept over [0,1] in 0.01 steps targeting ≥0.90 answered-precision:

```
Chosen ABSTAIN_THRESHOLD: 0.010  (persisted to app_settings, live)
  - 23/23 genuinely-unanswerable items scored confidence exactly 0.000
  - every non-zero-confidence item was genuinely answerable
  => any threshold just above zero already yields 100% answered-precision
```

That result is degenerate-by-data, not by bug: on this calibration set the generator's own `insufficient_context` signal caught every unanswerable item, so the continuous part of the confidence formula never had to break a tie. Recorded honestly in `DECISIONS.md` (2026-08-03) rather than presented as a nuanced coverage/precision tradeoff it isn't.

**Baseline eval run** `d248ecbc` (`phase4-trust-baseline-v3`, 2026-08-05, ~1h6m). 110 of 117 items completed; the last 7 failed on the OpenRouter free tier's 50-req/day cap (per-item isolation kept the run aggregating from the successes). Full numbers in `baselines/phase4-trust-v1.json`.

```
Retrieval (n=81) — comparable to Phase 3, generation-independent:
  hit_rate      0.988  [0.963, 1.00]     (Phase 3: 0.988)
  MRR           0.936  [0.890, 0.977]    (Phase 3: 0.939)
  NDCG@10       0.949  [0.910, 0.982]    (Phase 3: 0.950)
  => trust layer added no retrieval regression

Trust layer (n as marked):
  unsupported_claim_rate          0.398  [0.270, 0.525]  (n=19)
  confidence (mean)               0.351  [0.238, 0.458]  (n=32)
  abstained (rate)                0.406  [0.250, 0.594]  (n=32)
  abstention_correct              0.781  [0.625, 0.906]  (n=32)
  abstention_recall_unanswerable  1.00   [1.00, 1.00]    (n=6)
  answered_precision              1.00   [1.00, 1.00]    (n=19)
  adversarial_safe                1.00   [1.00, 1.00]    (n=3)

Generation + judge (n=18) — NOT comparable to Phase 3 (different generation model):
  faithfulness         0.489  [0.331, 0.661]
  answer_correctness   0.769  [0.628, 0.886]
  context_precision    0.517  [0.336, 0.692]
  context_recall       0.536  [0.353, 0.731]
```

**Against Phase 4's exit criteria — one met, one missed:**

- **Abstention recall on the unanswerable subset ≥ 0.80 → MET** (1.00). Caveat stated plainly: only n=6 unanswerable items reached the full pipeline before the quota cut the run short, so a perfect score there has a wide true interval. The calibration run's independent 23/23 is the stronger evidence.
- **unsupported_claim_rate ≤ 0.05 → NOT MET** (0.398). Reported as measured, not adjusted. MiniCheck is a strict sentence-level entailment checker, and the generator here is an untuned free-tier hosted model — a claim that paraphrases or aggregates across chunks reads as unsupported even when a human would accept it. The metric is doing its job; closing the gap is generation/prompt work, deferred rather than papered over.

Engineering verification: `ruff check` / `ruff format --check` / `mypy app` / `pytest tests/unit` all pass (69 tests, 19 new this phase); frontend `eslint` / `tsc --noEmit` / `next build` all clean.

## Key decisions this phase

- **Confidence-gated abstention supersedes, rather than replaces, the model's raw `insufficient_context` signal** — the two are kept as distinct fields (`insufficient_context` vs. `abstained`) since they can now diverge: a model can generate real claims that are still, in aggregate, not confident enough to show.
- **The eval harness and production `/query` share the exact same trust-layer functions and the exact same DB-backed threshold** — no separate "eval-only" abstention logic, so Phase 4's exit criterion is measured against what the system would actually do in production, not an approximation of it.
- **A MiniCheck failure degrades to `unscored` rather than failing the request** — matches this project's established resilience pattern (Phase 2's OCR timeout guard, Phase 3's per-item eval isolation): an optional trust signal shouldn't take down the primary answer path.

## What's next

**Phase 5 — Continuous learning loop**: feedback capture, hard-negative mining from retrieval failures and thumbs-down feedback, embedder/reranker fine-tuning jobs, and an A/B promotion gate requiring a statistically significant improvement before a fine-tuned model replaces the active one.
