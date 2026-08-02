# DECISIONS.md

Deviations from `SPEC.md`, recorded as they're made, per SPEC.md §0.3: "If a library choice in this spec fails/conflicts, prefer the simplest working alternative and record the decision here." Full rationale for each lives in `document/implementation-plan.md`; this file is the terse changelog.

---

## 2026-07-30 — Provider layer: self-hosted-first, not Gemini-only

**Spec said:** Gemini 2.5 Flash/Pro for generation, judging, and enrichment; `gemini-embedding-001` for embeddings (§2, §9).
**Decision:** `LLMProvider`/`EmbeddingProvider`/`RerankerProvider` interfaces speak an OpenAI-compatible API. Default generation = **Qwen3-4B-Instruct via Ollama** (runs natively on the Windows host, not in Docker, to keep model RAM off the WSL2 cap). Default embeddings = **`BAAI/bge-small-en-v1.5`, 384-dim**. Default reranker = **`cross-encoder/ms-marco-MiniLM-L-6-v2`**. A free (no-card) Google AI Studio key is used *only* for LLM-as-judge, golden-testset generation, and contextual enrichment — capped by a hard budget guard — since a 4B local model is weakest at those three offline, quality-critical jobs. Gemini remains available as a swappable provider for anyone who wants to run the full spec as written.
**Reason:** user cost constraint — paid LLM APIs for every generation call were ruled out.

## 2026-07-30 — Cloud budget: $0/month free-tier stack

**Spec said:** Cloud SQL (Postgres), GCS, Secret Manager, Cloud Run (§1.3, §2).
**Decision:** Cloud Run (scale-to-zero) + a free-tier Postgres with pgvector (Neon or Supabase) + a free-tier Redis (Upstash) for the ongoing public demo. GCS/Secret Manager usage kept inside free tiers or substituted.
**Reason:** user chose the $0/month option over paid GCP or trial credits.

## 2026-07-30 — Demo corpus: arXiv LLM/RAG papers

**Decision:** seed corpus is 30–50 arXiv papers on LLMs/RAG (not spec's generic "seed demo corpus").
**Reason:** recognizable to technical reviewers, stresses Docling (two-column layout, tables, math), freely redistributable.

## 2026-07-30 — 8GB-RAM/CPU-only local profile

**Decision:** all local-inference models sized for CPU on 8GB RAM (see `document/implementation-plan.md` §3): 4B-class quantized generator, 33M embedder, 23M reranker, RoBERTa-size NLI (MiniCheck). Ollama runs natively on Windows, not inside Docker. `docker-compose.yml` sets explicit `shm_size` on the postgres service.
**Reason:** user's available hardware.

## 2026-07-30 — Phase-2 exit gate fixed (spec circularity)

**Spec said:** Phase 2 exit = "NDCG@10 beats baseline-v0 on `ci_split`" (§10), but `ci_split.jsonl` and the eval harness don't exist until Phase 3 (§10 Phase 3).
**Decision:** Phase 1 ships a small hand-curated mini golden set (~20 items) + a deterministic `scripts/run_eval.py` (hit_rate@k, MRR, NDCG@10, no LLM judge) so `baseline-v0` has real numbers from day one and Phase 2 has something concrete to beat. Phase 3 formalizes into the full golden set + judge.

## 2026-07-30 — Streaming vs. structured generation output split

**Spec said:** structured JSON output (`answer_sentences[]` with citations) *and* an SSE streaming variant (§3.3) — these conflict; you can't stream prose and return strict JSON from the same call.
**Decision:** `POST /query` = non-streaming structured JSON. `POST /query/stream` = streams prose with inline citation markers (`[c12]`), parses sentences+citations at end-of-stream, runs claim verification, emits the trust payload as a terminal SSE event.

## 2026-07-30 — Golden dataset resized

**Spec said:** 200 full / 60 calibration / 50 CI-subset items (§8.3).
**Decision:** ~120 full (55 single-hop, 30 multi-hop, 25 unanswerable, 10 adversarial) / 40 calibration / 30 CI-subset.
**Reason:** keeps judge runtime and free-tier LLM-judge quota feasible on the self-hosted/hybrid setup while remaining statistically meaningful.

## 2026-07-30 — CI gates split into hard/soft

**Spec said:** all Section 7.2 metrics gate CI (§8.7).
**Decision:** deterministic retrieval metrics (hit_rate, NDCG, etc.) hard-fail CI; LLM-judge metrics (faithfulness, answer_correctness) soft-fail/warn or use a 2-run median.
**Reason:** LLM-judge scores are noisy enough that hard-gating on them would fail PRs randomly.

## 2026-07-30 — Latency & filtering architecture (research-informed)

**Trigger:** a claim that pgvector metadata pre-filtering beats post-filtering (12ms/45ms/18ms-style numbers) for vector search at scale. Dedicated research (`document/research-latency-optimization.md`) found the specific numbers unsourced but the underlying pgvector failure mode real and documented in pgvector's own README.
**Decision:**
- `hnsw.iterative_scan = relaxed_order` set as default for filtered queries (pgvector ≥0.8.0); partial HNSW indexes added for known low-cardinality metadata filters; pgvector pinned **≥0.8.2** (buffer-overflow CVE fix).
- `halfvec` (fp16) storage adopted for the embedding column.
- A **multi-architecture sweep** (filtering strategy × quantization × `ef_search` × concurrency) is run on our own data/hardware rather than assuming any single source's recommended config — see `document/implementation-plan.md` §2.E4.
- A large-scale synthetic benchmark (separate from the small real demo corpus) uses a real public embedding dataset (`abokbot/wikipedia-embedding`, 384-dim, dimension-matched to our own embedder) with our own chunks unioned in as "needle" vectors — not random synthetic vectors.
- **Capped at ~250K–500K vectors, built locally, $0** — a full 1M-vector HNSW index needs ~10–25GB RAM with graph overhead, not feasible on the 8GB local machine; no cloud VM spend was approved for this.
**Reason:** user wants a defensible, reproducible "least latency, solid numbers" resume claim; research showed no single filtering approach wins at every selectivity, so the honest approach is to measure and report the sweep, not assert one config.

## 2026-07-30 — Frontend: Next.js 16.2.12 / React 19, and a flat-config fix

**Spec said:** Next.js 14+ (§2).
**Decision:** scaffolded with **Next.js 16.2.12 / React 19** instead (14 predates current stable by several majors; spec's "14+" already permits this). During Phase 0 verification, `eslint.config.mjs` built with the documented `FlatCompat` + `compat.extends("next/core-web-vitals", "next/typescript")` pattern crashed (`TypeError: Converting circular structure to JSON` inside `@eslint/eslintrc`) — `eslint-config-next@16.2.12` no longer exports legacy named configs for that bridge; it exports a flat-config array directly (`export = config: Linter.Config[]`). Fixed by importing it directly: `import nextConfig from "eslint-config-next"; export default [...nextConfig]`. `@eslint/eslintrc` dependency removed as unnecessary.
**Reason:** ecosystem has moved past the FlatCompat pattern still shown in some older tutorials; discovered by actually running `npm run lint` during Phase 0 verification rather than assuming the scaffold worked.

## 2026-07-30 — Known, accepted dev-tooling vulnerabilities (non-blocking)

`npm audit` reports 12 high-severity findings on the frontend, all in build-time/lint tooling, not runtime code we control:
- `postcss`/`sharp` vendored **inside Next.js 16.2.12 itself** (`next/node_modules/...`) — already latest stable; no newer release fixes this yet.
- `eslint-plugin-react`/`-import`/`-jsx-a11y` (via `eslint-config-next`) pull an old `minimatch`/`brace-expansion` — fixing requires an eslint 10 major bump that `eslint-config-next` doesn't yet declare support for.
**Decision:** accepted for now; re-check each phase close (`npm audit`) and bump when upstream catches up. Not forcing `npm audit fix --force`, which would downgrade `next` to `9.3.3` or `eslint` to a version `eslint-config-next` doesn't officially support — either would break more than it fixes.
**Reason:** these are dev-time supply-chain findings with no exposure through the deployed app's runtime attack surface; forcing fixes now would trade a cosmetic audit score for real breakage.

## 2026-07-31 — Generation: plain prose + parsed citations, not JSON-schema-constrained output

**Spec said:** structured output via a JSON schema (§3.3): `{"answer_sentences": [...], "insufficient_context": bool}`.
**Decision:** drop Ollama's `format` (JSON-schema-constrained/grammar) decoding entirely; the model generates plain prose with inline `[chunk_id=<id>]` citation markers, parsed into the same `GeneratedAnswer`/`ClaimOut` shape by `app/generation/parser.py`. `LLMProvider.generate_json(...)` became `LLMProvider.generate(...) -> LLMResult(text=...)`.
**Reason:** empirically, under grammar-constrained decoding our 4B local model (`qwen3:4b-instruct`) reliably took the trivial shortcut the schema didn't forbid — an empty `answer_sentences` array + `insufficient_context: true` — on a question the retrieved context clearly answered. The *identical* prompt/context with unconstrained plain-text generation answered correctly, cited correctly (in the exact `[chunk_id=...]` format asked for), and ran roughly 6x faster (~30-38s vs 235s+/timeout). This also collapses the earlier planned split between `POST /query` (structured) and `POST /query/stream` (prose + parsed markers, amendment A2) into one shared generation approach.
**Also fixed along the way (kept, though superseded as the primary fix):** Ollama defaults to a 4096-token context window regardless of what the model supports — added `OLLAMA_NUM_CTX` (default 8192) and `GEN_TIMEOUT_SECONDS` (default 300, later 600 — CPU inference of a large context is genuinely slow and varies run to run) to `config.py`.

## 2026-07-31 — Backend Docker build/runtime fixes (Phase 1 dependency additions)

Three build/runtime issues surfaced adding docling/sentence-transformers/torch for Phase 1, none in SPEC.md scope but each needed a real fix:

- **CPU-only torch wheel, not PyPI's default.** `pip install torch` pulls a ~530MB CUDA-bundled wheel that repeatedly stalled mid-download through Docker Desktop's network layer on this machine (reproduced twice). Fixed by installing `torch torchvision` together from `https://download.pytorch.org/whl/cpu` *before* the main `pip install -e ".[dev]"` step (torchvision pinned alongside torch, not separately, after installing torch alone first caused a version-mismatched `torchvision::nms does not exist` RuntimeError). Also just correct for our CPU-only profile — no CUDA runtime we'll ever use.
- **`libxcb1` and friends for Docling's table-structure model.** Docling's `docling_ibm_models` table-former model imports `cv2` (opencv), which needs `libgl1 libglib2.0-0 libxcb1 libxext6 libsm6 libxrender1` — absent from `python:3.12-slim`. Without them Docling's table model fails to initialize and the ingestion pipeline silently falls back to pypdf (still works, just loses Docling's layout/table fidelity, the whole reason arXiv two-column PDFs were chosen as the demo corpus). Added to the Dockerfile's `apt-get install` line; confirmed via a real re-ingest that `parser` flips from `pypdf` to `docling`.
- **Celery per-task event loop vs. a shared async engine pool.** `ingest_document_task` wraps each call in its own `asyncio.run()` (a fresh event loop every task), but `app/db/session.py`'s async engine/connection pool is a module-level singleton created once at worker startup. asyncpg connections are tied to the loop they were created on, so a pooled connection from task N's (now-closed) loop reused in task N+1 raised `RuntimeError: ... attached to a different loop`. Fixed by calling `await engine.dispose()` in a `finally` block after each task, forcing the next task to open fresh connections on its own loop. Caught mid-seed-run (6/13 documents had failed with this error); fixed, then a clean re-run ingested 36/40 papers with zero recurrences, the remaining 4 finishing shortly after their client-side polling timeout (a script issue, not a task failure — the worker had already completed them).

## 2026-07-31 — Citation parser: reattach trailing citations across a sentence-punctuation boundary

**Found via unit tests** (`backend/tests/unit/test_parser.py`), not manual testing: a naive sentence splitter (`re.split(r"(?<=[.!?])\s+", text)`) breaks when the model places a citation marker *after* a sentence's punctuation with a space in between (e.g. `"Both sources agree. [chunk_id=chunk-a][chunk_id=chunk-b]"`) — the split fires at the first `". "`, orphaning the citation-only fragment into its own "sentence" with no real text, which then gets silently dropped (`if clean_text:` guard). Fixed by using a capturing group in the split pattern (`(?<=[.!?])((?:\s*\[chunk_id=[^\]]+\])*)(?:\s+|$)`) so `re.split` interleaves the captured trailing-citation text back into the output list, then reassembling each sentence with the citation blob that followed it. The `(?:\s+|$)` alternation (not just `\s+`) matters too — without allowing end-of-string as a valid terminator, Python's greedy-then-backtrack regex engine backs off to matching zero citations just to satisfy a trailing whitespace requirement that can't be met at the end of the text.
**Reason this matters:** exactly the kind of thing that "looks like it works" in a couple of manual spot-checks (both real end-to-end tests happened to hit the case this bug didn't break) but silently drops citations in a systematic, reproducible way for a specific — and plausible — model output pattern. Real unit tests over the deterministic parsing logic caught it; manual testing alone had not.

## 2026-08-01 — `tsv` GENERATED ALWAYS column needs `Computed()` in the ORM model, not just the migration

**Found mid-reindex** (1/40 documents failed): the migration adds `chunks.tsv` as `GENERATED ALWAYS AS (to_tsvector('english', content)) STORED`, but the SQLAlchemy `Chunk` model declared it as a plain `mapped_column(TSVECTOR, nullable=True)`. SQLAlchemy doesn't know the column is DB-computed, so on some code paths it included an explicit `tsv=NULL` in the INSERT — Postgres rejects any explicit value (even NULL) for a `GENERATED ALWAYS` column: `cannot insert a non-DEFAULT value into column "tsv"`.
**Fix:** `mapped_column(TSVECTOR, Computed("to_tsvector('english', content)", persisted=True), nullable=True)` — `Computed()` tells the ORM to never include the column in INSERT/UPDATE at all.

## 2026-08-01 — halfvec migration must land before the model changes, not after

**Self-inflicted sequencing bug:** edited `Chunk.embedding` to `HALFVEC(384)` before running migration `0004_halfvec_migration` (which converts the actual `embedding` column from `vector(384)` to `halfvec(384)` and rebuilds the HNSW index with `halfvec_cosine_ops`). Caught by checking `alembic_version` (still `0003`) against the model's already-`HALFVEC` declared type before any data corruption occurred — stopped the in-progress reindex, ran migration 0004, restarted the worker, redid the reindex clean.
**Lesson:** when a migration changes a column's storage type, run and verify it *before* touching the ORM model, not alongside it — the two must never be out of sync even briefly during a live reindex.

## 2026-08-01 — Docling/RapidOCR has no internal timeout; a thread-based wall-clock guard isn't enough either

**Found on real data, twice:** one corpus document (`2410.12311v4`) drove Docling's automatic RapidOCR fallback for 5+ hours with no completion (confirmed genuinely computing via `docker stats`, ~380% CPU, not deadlocked) — Docling has no internal timeout for OCR.
**First fix:** wrap the parse in `concurrent.futures.ThreadPoolExecutor(max_workers=1)` + `future.result(timeout=DOCLING_TIMEOUT_SECONDS)`, falling back to pypdf on `TimeoutError`. This unblocked the pipeline correctly — but Python cannot forcibly kill a thread, so the abandoned OCR work kept running in the background indefinitely.
**Found live, independently, later in the same phase:** after a Docker Desktop restart and worker recovery, `docker stats` showed the worker container pinned at ~900% CPU with an *empty* Celery queue — the orphaned thread from an earlier timeout was still burning CPU forever, invisible to Celery (which had already moved on) and invisible to `celery inspect active` (which only sees task-level state, not the runaway thread inside a completed task).
**Real fix:** replaced the thread with a genuine child OS process (`multiprocessing.Process` + a result `Queue`, `process.join(timeout=...)`, `process.kill()` on timeout). A process can be SIGKILLed and its CPU actually reclaimed by the OS; a thread cannot. Verified live: worker CPU dropped from ~380–800% to 0.07% in the same instant the timeout fired and the pypdf fallback completed, and `docker compose logs worker` showed the OCR attempt running under a distinct `Process-1` name, killed cleanly at the 300s mark.
**Reason this matters:** the first fix looked complete (pipeline unblocked, task "succeeded", fallback worked) and shipped with an honest comment about the tradeoff — but "the task moved on" and "the resources were reclaimed" are different guarantees, and only load-bearing production behavior (CPU pinned at 900% with nothing queued) surfaced the gap between them.

## 2026-08-01 — pgvector's documented filtered-search bug doesn't reproduce on the real corpus at its actual size — and why that's the correct planner behavior

**Investigated for the Phase 2 exit criterion** ("a recall@k/latency curve reproduces then fixes pgvector's documented filtered-search failure mode, measured on the real corpus"). Running the sweep script as originally written (`backend/scripts/benchmark_filtering.py`) against a real per-document filter (2.0% selectivity, 30/1532 chunks) returned the full requested `top_k=10` at every `ef_search`/`hnsw.iterative_scan` combination — no bug, no curve.
**Root cause, confirmed via `EXPLAIN ANALYZE`:** at ~1.5K chunks, Postgres's own cost-based planner never chooses the HNSW index for this query shape at all — it picks a `Bitmap Heap Scan` on the `document_id` B-tree index (or, with bitmap/seq scan disabled, a plain `Index Scan` on the same B-tree, or with that index also gone, a full `Seq Scan`) followed by an *exact* sort, because at this table size any exact path is cheaper than the approximate ANN index. The bug is real but structurally unreachable below some corpus-size threshold — the planner sidesteps it correctly, on its own, without any GUC involved.
**To still exercise and fix the documented bug on real data:** the benchmark script now drops the competing `ix_chunks_document_id` index and sets `enable_seqscan = off`, both scoped to a transaction it always rolls back (never committed — restored even on a crash), forcing the planner onto `Index Scan using ix_chunks_embedding_hnsw`. This reproduces the bug cleanly: with `hnsw.iterative_scan = off`, **0 of the requested 10 rows** come back at every `ef_search` value tested (10/40/80/160) — the 30 chunks belonging to the filtered document simply aren't among the HNSW graph-traversal candidates. Switching to `iterative_scan = relaxed_order` fixes it to a reliable **10/10** at every `ef_search` value, at a measured ~3–4x latency cost (≈1–2ms → ≈4–6ms) — cheap insurance against silently incomplete results.
**Decision:** ship both halves of the finding — the "natural" plan (proof the bug doesn't threaten this corpus today) and the "forced" plan (proof it will threaten a larger one, and that the fix works) — rather than reporting only whichever one made the exit criterion easier to claim. `hnsw.iterative_scan = relaxed_order` stays the default per the 2026-07-30 filtering-architecture decision; this is corroborating evidence at real-corpus scale, not new fallout from it.

## 2026-08-01 — Phase 3 golden-set generation and judging stay self-hosted-only for now

**Spec/kickoff said:** a free Google AI Studio (Gemini) key powers golden-testset generation and LLM-as-judge scoring, since the 4B local model is spec-identified as weakest at exactly those two offline jobs (2026-07-30 provider-layer decision).
**Decision:** asked the user directly rather than silently defaulting; chose to proceed fully self-hosted (`qwen3:4b-instruct` via Ollama for both testset generation and judging) rather than set up a Gemini key right now. `JUDGE_PROVIDER=ollama` was already the config default, so no code change was needed — only the golden-set-generation script, which is new this phase.
**Consequence:** judge scores (faithfulness, answer_correctness, context_precision/recall) and generated golden-set questions reflect the weaker local model's judgment/creativity, not Gemini's. The `JudgeProvider`/generation-script LLM dependency is injected, not hardcoded, so swapping in a Gemini-backed provider later needs no harness changes — only a re-run.

## 2026-08-01 — Golden-set generation: two real data-quality bugs, found by inspecting output before trusting it

Both found by spot-checking generated items rather than assuming a "looks like it ran fine" script output was good data — same lesson as the citation-parser and tsv findings earlier in this project.

1. **Reference-list chunks make bad single/multi-hop source material.** The corpus-chunk sampler (`token_count >= 150`) happily selected a bibliography chunk (a block of citation entries), and the model dutifully wrote a plausible-sounding question about *a citation's title* rather than the paper's own argument — technically "answerable" but not a meaningful RAG eval item. Fixed with a heuristic filter (`_looks_like_references`: 2+ URLs, or 4+ `Lastname, X.`-pattern author-list matches) applied before a chunk is offered to the generator, with oversampling + retry so the target count is still reached.
2. **`GEN_TEMPERATURE=0.1` (the app-wide generation default, reused as-is by the golden-set generator) collapsed "unanswerable" question diversity.** Of 25 generated unanswerable items, 17 were near-duplicates of one topic ("IoT sensor data integration") — a shuffled corpus-title list alone wasn't enough perturbation to escape the model's single strongest low-temperature completion for "plausible but out-of-corpus RAG question." Caught by word-overlap (Jaccard ≥0.55) deduplication during curation (`scripts/curate_golden_set.py`), which dropped the duplicates and backfilled the shortfall one item at a time, each call explicitly listing every already-used topic to avoid — a directive constraint the model reliably honors even at the same low temperature, unlike passive shuffling.

## 2026-08-01 — Phase 3 eval-harness schema: `eval_runs.metrics` added beyond SPEC.md §5's table

**Spec said:** `eval_runs` = `id, dataset_version, config jsonb, git_sha, started/finished, status` — no aggregate-metrics column; `eval_results.metrics jsonb` holds per-question metrics.
**Decision:** added `eval_runs.metrics jsonb` (nullable, populated on completion) as a run-level aggregate (bootstrap mean/CI per metric, `app/evals/bootstrap.py`), so the Evaluations page's runs list and CI regression checks don't need to re-aggregate every `eval_results` row on each load.
**Reason:** small, additive, backward-compatible with the spec'd shape; avoids an O(n) recomputation for a value that's cheap to compute once at the end of a run and never changes after.

## 2026-08-01 — Full generation+judge pass runs on a documented subset, not all ~120 golden-set items

**Spec implied:** every golden-set item gets full metrics (retrieval + generation + judge).
**Decision:** `POST /api/eval/run` always computes retrieval metrics (hit_rate/MRR/NDCG@10) for the full golden set — cheap, no generation needed. Generation+judge metrics (faithfulness, answer_correctness, context_precision/recall, abstention) run on a `full_pipeline_ids` subset the caller specifies; the harness itself imposes no cap. For `baselines/baseline.json`'s Phase 3 baseline, that subset is every 3rd item of the shuffled `eval-datasets/v1/full.jsonl` (~40 items, stratified by construction since the file is pre-shuffled across types).
**Reason:** measured single-item full-pipeline latency (main generation + judge call) at roughly 150–450s on this 8GB CPU-only local profile (implementation-plan.md B4); a full ~120-item pass would run 8–12+ hours for one baseline. ~40 items is enough for a bootstrap CI with a meaningful sample while keeping one baseline run to a few hours — consistent with this project's established practice of disclosing hardware-driven scope tradeoffs rather than silently running a smaller "full" set.

## 2026-08-01 — `evals.yml` CI gate: a fixture-corpus smoke test, not literally SPEC.md §8.3's "30-item CI subset"

**Spec said:** `evals.yml` runs eval on `ci_split.jsonl` (a 30-item subset of the real golden set) per PR, full set nightly, gated per Section 7.2's regression rules.
**Decision:** a real `eval-datasets/v1/ci_split.jsonl` (30 items, a real subset of the curated golden set v1) exists and is meant for fast local/manual retrieval-only checks against the real corpus — but the actual GitHub Actions `evals.yml` workflow uses a separate, clearly-labeled tiny synthetic fixture corpus (`scripts/generate_ci_fixtures.py`: 4 one-topic hand-rolled PDFs + `eval-datasets/ci-fixture/golden.jsonl`, 5 items) that it ingests fresh and queries end-to-end on every PR, hard-failing if any answerable fixture question doesn't retrieve its one obviously-correct document at rank 1.
**Reason:** the real golden-set-v1 needs the real 40-document corpus already ingested, embedded, and HNSW-indexed — rebuilding that from scratch on a free GitHub-hosted runner on every PR is not feasible (Docling/embedding time, no persistent volume). No LLM/judge runs in this CI job either, for the same reason Ollama isn't installable-and-warm cheaply in a stock runner. This *is* a real, working, automatic regression gate — a genuinely broken retrieval pipeline fails it — but it cannot catch subtler quality regressions the way a full `POST /api/eval/run` against the real corpus would; that stays a manual/local check against the persistent dev stack for now.
**Also found while building this:** the hand-rolled fixture PDFs (no PDF-writing dependency was added just for 4 tiny files — see the generator's own docstring) sometimes read as "scanned" to Docling's layout model and fall into its OCR path, confirmed live (3 of 4 fixtures fell back to pypdf, 1 succeeded via Docling). `DOCLING_TIMEOUT_SECONDS=10` in the CI job keeps this fast — the always-correct pypdf fallback (Phase 2's timeout-guard work) makes the parser choice irrelevant to correctness either way.

## 2026-08-02 — Eval runner: per-item failure isolation, and a longer generation timeout for background runs

**Found running the actual Phase 3 baseline eval**, twice: the first attempt died after ~10 minutes with `run.status="failed"` and an *empty* error message — `except Exception as e: run.error = str(e)` stored nothing useful because the exception itself (in this case) had no informative `str()`. Fixed the diagnosis gap first (`logger.exception(...)` + `traceback.format_exc()` in the stored error), then re-ran to get a real answer: `httpx.ReadTimeout` inside `OllamaProvider.generate()` — a multi-hop item's larger assembled context (two source excerpts, expanded to parents) pushed generation past `GEN_TIMEOUT_SECONDS=600`, the live-query default.
**Two separate fixes, both real:**
1. `OllamaProvider.__init__` now takes an optional `timeout` override (defaults to the existing `settings.GEN_TIMEOUT_SECONDS` when omitted, so the live `/api/query` path is unchanged). The eval Celery task constructs it with `timeout=1200.0` — eval runs are background/non-interactive and can afford to wait much longer than an interactive request ever should.
2. **The bigger fix**: `execute_eval_run`'s per-item loop wasn't isolated — one item's exception aborted the whole run, discarding every already-committed `EvalResult` from ever being aggregated (the rows survived in the DB, since each item commits individually, but `run.metrics` never got computed and the run showed `status="failed"` with zero visible signal). Moved the try/except inside the loop: a failing item is logged, rolled back, and recorded in a `failures` list; the run still completes and aggregates from whatever succeeded, only falling back to `status="failed"` if *every* item failed. `run.error` on an otherwise-`completed` run now doubles as a non-fatal "N/M items failed: [...]" advisory.
**Reason this matters:** a harness that can't tolerate one slow or genuinely-timed-out item among ~40 is too fragile to trust for a real baseline number — the whole point of computing a bootstrap CI over many items is that a handful of outliers shouldn't invalidate the run.
