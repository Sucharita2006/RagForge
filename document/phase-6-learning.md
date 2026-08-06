# Phase 6 — Learning Flywheel

**Status:** complete (exit criterion met — the gate refused a real candidate on measured evidence)
**Date:** 2026-08-06
**Spec reference:** `SPEC.md` §10 Phase 6, §3.5, §3.9 page 8
**Acceptance criteria:** a fine-tuned reranker can be trained from feedback, and promotes **only** if its ΔNDCG CI excludes 0.

## Goal

Close the third loop: let the system improve its own retrieval from its own usage, and — critically — make it impossible for that improvement to be *assumed*. A candidate model ships only when a measured A/B says it's better.

Scope decision made upfront (see "Key decisions"): build and prove the loop on the **reranker** first. It's the cheaper half — no corpus re-embedding, retrieval-only evaluation — so the flywheel gets validated end-to-end before the more expensive embedder path is attempted.

## What was built

- **Feedback capture** (`POST /api/feedback`, thumbs UI on the Playground): rating plus optional free-text correction, linked to the answer and — through `answers.trace_id` — to the Phase 5 span waterfall that produced it.
- **Training-pair mining** (`app/learning/mining.py`, `scripts/mine_training_pairs.py`):
  - *Golden-set pairs*: the positive is the top-ranked chunk belonging to the item's **expected** document — independent evidence, not the retriever agreeing with itself. Hard negatives are the highly-ranked chunks from *wrong* documents.
  - *Feedback pairs*: only corrections are used. A bare thumbs-down identifies wrong chunks but not the right one, so it yields negatives with no positive and cannot form a triple; those go to failure clustering instead of having a positive invented for them.
  - *Round-trip filter* for synthetic pairs (SPEC.md §3.5): a generated query is kept only if retrieving it actually surfaces its own source chunk.
- **Reranker fine-tuning** (`app/learning/finetune.py`, `finetune_reranker` Celery task): CrossEncoder training on (query, passage, label) examples fanned out from each pair (1 positive + N negatives). Training deps are imported function-locally so only the worker loads them; the fit runs via `asyncio.to_thread` so a multi-minute CPU job never holds a DB connection.
- **Model registry** (`model_registry` table): every run recorded with its artifact, train config, and measured eval metrics. A partial unique index enforces **one active model per kind in the database**, not merely in application code — verified by confirming Postgres rejects a second active row.
- **Hot-swappable loading** (`app/retrieval/rerankers/registry.py`): the pipeline resolves the active model from the DB per retrieval, so promotion is a DB write rather than a redeploy — and the Celery worker (a *separate process*) picks it up without restarting. The model itself is still loaded once per distinct path via `lru_cache`.
- **A/B promotion gate** (`app/learning/promotion.py`, `POST /api/models/{id}/promote`): reuses Phase 5's paired-bootstrap `compare_runs`, so the gate and the Experiments page cannot disagree about what an improvement is. Promotes only if ≥1 gate metric significantly improved **and** none significantly regressed.
- **Failure clustering** (`app/learning/clustering.py`): buckets recent failures into SPEC.md §5's four labels with a suggested action each. Failure signal comes from negative feedback *and* abstentions — counting only the former would under-report by exactly the amount the trust layer is working.
- **Learning page**: model registry with a gate-enforced promote button, failure clusters, recent feedback.

## What changed from the original design (and why)

1. **Train/test contamination, caught before it produced a fake number.** The first mining pass drew pairs from all 84 answerable golden-set items — the same items the A/B gate scores. Training and evaluating on the same questions would have made any "improvement" a measure of memorization, and the gate rigorous in form but worthless in substance. Fixed with a deterministic split; the 84 contaminated pairs were **deleted**, not reused.
2. **Split by `id` hash, not seeded shuffle.** A seeded shuffle depends on input ordering, so a re-mine or re-export could silently move an item across the boundary and leak it. Hashing the id is stable regardless of file order.
3. **`reranker_path` threaded through the whole retrieval path** (`retrieve()` → eval runner → Celery task → `POST /api/eval/run` via `reranker_model_id`). Without it a candidate could only be evaluated *after* being promoted — i.e. the gate would require shipping the model it exists to judge.
4. **The Celery worker does not auto-reload.** The first fine-tune request was rejected with `KeyError: 'finetune_reranker'`: the API runs `uvicorn --reload` and picked up the new code instantly, but the worker had never registered the new tasks. A distinct gotcha from Phase 5's (where `--reload` was too *aggressive* and killed in-flight requests); here the opposite process wasn't reloading at all.

## Key decisions this phase

- **Reranker before embedder.** An embedder swap invalidates every stored vector and forces a full re-embed of the corpus before evaluation can even begin; the reranker needs neither. Proving the flywheel on the cheaper path first means the promotion gate is trusted before it's pointed at the expensive one.
- **The endpoint enforces the gate; there is no override flag.** A promotion that can be forced by passing a parameter is not a gate. A refused promotion returns **200 with the reason and the per-metric CI table** — the gate correctly declining a weak candidate is a successful outcome of asking, not a failed request.
- **Gate metrics are retrieval-only** (`ndcg@10`, `hit_rate`). A reranker cannot improve faithfulness except through retrieval, so including generation metrics would add noise — and a dependency on which generation provider happened to run — to the decision.
- **Fine-tuning registers a `candidate`, never `active`.** Training and promoting are deliberately separate operations, so a training run cannot silently become production without being evaluated.
- **Re-mining clears prior mined pairs.** Hard negatives are defined relative to the *current* ranker; keeping stale ones would train the next model against confusions its predecessor already fixed.
- **Local fine-tuning, no cloud GPU** — justified by measurement, not assumption (see Verification).

## Verification (measured, this session)

The full loop was run end-to-end on the real corpus: **mine → train → evaluate → gate**.

**1. Split (contamination control).** `scripts/split_golden_set.py`, hash-based, asserts zero overlap:

```
source   : 117 items (84 answerable)
train    :  66 items (47 answerable)   <- mining/training only
held-out :  51 items (37 answerable)   <- A/B gate only
```

**2. Mine.** 47 pairs with 185 hard negatives from the *train* split → **232 cross-encoder examples**. (An earlier run against the full set produced 84 pairs; those were deleted, not reused — see "What changed".)

**3. Train.** CrossEncoder fine-tune, 2 epochs, batch 32, **129.5s** on CPU — consistent with the pre-flight benchmark (~30 pairs/s, ~1.5GB peak) that justified training locally rather than on a cloud GPU. Registered as `candidate`.

**4. Evaluate,** both on the held-out split (n=37 answerable), the candidate scored via `reranker_model_id` *without being promoted first*:

```
                 ACTIVE (baseline)    CANDIDATE (fine-tuned)
ndcg@10          0.9576               0.9360
hit_rate         0.9730               0.9730
reciprocal_rank  0.9527               0.9234
```

**5. Gate — refused:**

```
PROMOTED: False
REASON  : no gate metric improved with a 95% CI excluding 0
          (the candidate is not measurably better)

metric        delta            95% CI        n   significant  improved
ndcg@10     -0.0216   [-0.0586, +0.0037]    37   False        False
hit_rate    +0.0000   [+0.0000, +0.0000]    37   False        False
```

Post-gate state verified: the candidate remained `candidate`, the baseline remained `active`, and `active_reranker_path()` still resolves to the baseline. **Nothing shipped.**

### Reading this result honestly

The exit criterion is *"promotes only if ΔNDCG CI excludes 0"* — and the gate refused a real, freshly-trained model on real measured evidence. That is the criterion met, not a failed experiment.

Three things are worth stating plainly rather than dressed up:

- **The candidate is genuinely not better.** Its NDCG point estimate is *lower* (−0.0216). The CI straddles zero, so it isn't a significant regression either — this is noise, not a win, and the gate treats "not distinguishable from the incumbent" as "don't ship", which is the correct default.
- **This outcome was likely from the start, and the setup was not adjusted to avoid it.** 47 training pairs is a very small dataset, and the baseline already scores 0.958 NDCG@10 on held-out — there is almost no headroom. The honest framing is that this run proves the *mechanism*, not that fine-tuning helps at this data scale.
- **The positive path is covered by unit tests, not by a fabricated model.** `test_promotion_accepts_a_real_significant_improvement` asserts the gate promotes on a clean improvement, alongside tests that it refuses regressions, no-change, noise-that-averages-upward, and mixed win/regression. Manufacturing a "better" model to demo a green promotion would have proven nothing about the gate.

What would plausibly change the result: substantially more training pairs (synthetic generation over the whole corpus rather than only golden-set items), and a baseline with more headroom to improve on.

Engineering verification: `ruff check` / `ruff format --check` / `mypy app` clean (100 source files); `pytest tests/unit` **101 passed** (11 new gate/clustering tests this phase); frontend `eslint` / `tsc --noEmit` clean.

## What's next

**Phase 7 — Security layer**: ingest-time sanitizer + quarantine, spotlighting at generation, output guard, and a red-team corpus + runner reporting Attack Success Rate per category, with an ASR regression gate wired into CI.
