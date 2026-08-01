# Phase 2 — Full Retrieval Engine

**Status:** complete
**Date:** 2026-08-01
**Spec reference:** `SPEC.md` §10 Phase 2
**Acceptance criteria:** `/api/retrieve` shows all four score types (dense/sparse/RRF/rerank), NDCG@10 beats `baseline-v0`, and a recall@k/latency curve reproduces then fixes pgvector's documented filtered-search failure mode, measured on the real (not synthetic) corpus.

## Goal

Take Phase 1's dense-only retrieval and turn it into the full multi-stage engine: sparse full-text search fused with dense via RRF, cross-encoder reranking, parent-child chunking with context expansion, lost-in-the-middle reordering, session-aware query rewrite, a semantic cache, incremental re-ingestion, and the `vector` → `halfvec` storage migration — all measured against Phase 1's real `baseline-v0` numbers, not asserted.

## What was built

- **Sparse FTS** (`app/retrieval/sparse.py`): a DB-computed `tsvector` column (`GENERATED ALWAYS AS to_tsvector('english', content) STORED`, GIN-indexed) searched via `websearch_to_tsquery` + `ts_rank_cd`.
- **RRF fusion** (`app/retrieval/fusion.py`): reciprocal rank fusion over the dense and sparse ranked lists, preserving each candidate's individual dense/sparse rank and score for inspector display.
- **Cross-encoder reranking** (`app/retrieval/rerankers/`): a `RerankerProvider` interface with a `cross-encoder/ms-marco-MiniLM-L-6-v2` implementation, reranking the RRF-fused candidate set.
- **Parent-child chunking**: children are the searchable unit (dense + sparse); a matching child's parent is swapped in for context assembly (`expand_to_parents`), deduplicating when multiple ranked children share a parent.
- **Lost-in-the-middle reorder** (`app/retrieval/assembly.py`): best-ranked chunks placed at the start and end of the assembled context, worst-ranked buried in the middle, before formatting — citation hygiene still checks against the original rank order.
- **Session-aware query rewrite** (`app/retrieval/query_transform.py`): resolves pronouns/references against recent session history via the LLM; skipped entirely (no LLM call) when a session has no prior turns.
- **Semantic cache** (`app/retrieval/cache.py`): Redis-backed, brute-force cosine similarity over cached query embeddings, keyed against a `corpus_version` counter that's bumped on every ingest/reindex so a cache entry can never survive a corpus change it wasn't computed against.
- **Incremental re-ingestion**: content-hash diffing at re-embed time reuses embeddings for chunks whose content didn't change; `POST /documents/{id}/reindex` drives it.
- **Contextual enrichment** (`app/ingestion/enrich.py`, `app/providers/llm/gemini.py`): a free-tier Gemini REST call to generate a `context_prefix` per chunk — feature-flagged, requires `GOOGLE_API_KEY`, dormant without one.
- **`vector` → `halfvec` migration**: embedding column and HNSW index (`halfvec_cosine_ops`) both migrated; `hnsw.ef_search`, `hnsw.iterative_scan`, `hnsw.max_scan_tuples` set per-query via `SET LOCAL`.
- **Retrieval Inspector** (`frontend/app/retrieval-inspector/`): a debug UI surfacing all four score types per candidate, built on the existing `/api/retrieve` debug endpoint.
- **Filtering benchmark** (`backend/scripts/benchmark_filtering.py`): sweeps `ef_search` × `iterative_scan` against the real corpus to reproduce and fix pgvector's documented post-filter bug — see "What changed" below for why the naive version of this script didn't initially show anything.
- **Tests**: `test_fusion.py`, `test_enrich.py` (new), `test_assembly.py` extended for parent expansion and lost-in-the-middle reorder — 27 unit tests total, up from 19 in Phase 1.

## What changed from the original design (and why)

Full rationale in `DECISIONS.md`; summary of what surfaced only once this ran against real data and real infrastructure:

1. **`tsv` needs `Computed()` in the ORM model, not just the migration.** SQLAlchemy doesn't know a plain `mapped_column` is DB-computed and can send an explicit `NULL` for it — Postgres rejects any explicit value for a `GENERATED ALWAYS` column. Caught mid-reindex (1/40 documents failed); fixed by adding `Computed(...)` to the mapped column.
2. **A self-inflicted migration-sequencing bug**: edited the ORM model to `HALFVEC` before running the migration that actually converts the column. Caught by checking `alembic_version` against the model's declared type before any data was touched; fixed by stopping, migrating properly, then redoing the reindex.
3. **Docling/RapidOCR has no internal timeout, and a thread-based guard isn't enough.** One document drove OCR for 5+ hours (genuinely computing, not deadlocked). A `ThreadPoolExecutor` + wall-clock timeout unblocked the *pipeline* correctly but couldn't kill the underlying thread — later observed live as the worker container pinned at ~900% CPU with an empty Celery queue, an orphaned OCR thread from an earlier timeout still running invisibly. Fixed by running the parse in a real child *process* (`multiprocessing.Process`), which can be SIGKILLed and its CPU actually reclaimed — verified live: CPU dropped from ~400-800% to 0.07% in the same instant the timeout fired.
4. **pgvector's documented filtered-search bug doesn't reproduce on this corpus at its actual size — and that's the planner working correctly.** The benchmark script as originally written showed a flat `avg_rows=10.0` across every `ef_search`/`iterative_scan` combination — no bug. `EXPLAIN ANALYZE` showed why: at ~1.5K chunks, Postgres's own cost-based planner never picks the approximate HNSW index for a selective `document_id` filter — an exact B-tree-filtered scan is just cheaper. To still exercise and fix the real bug, the benchmark now forces the HNSW path (drops the competing index + disables seq scan, both scoped to a transaction that's always rolled back) — see "Verification" below for the resulting numbers.
5. **Client-side request timeouts don't cancel server-side generation.** Repeated manual test calls with a client `--max-time` cutoff appeared to "fail," but the underlying Ollama call kept running to completion server-side and got cached — later showing up as an unexpected fast cache hit. Not a product bug (single-user demo flow), but a real gap a multi-user deployment would need to close via actual request cancellation.

None of these are scope changes to what Phase 2 delivers — all were found and fixed by actually running the full pipeline against the real 40-paper corpus rather than stopping once the code looked right.

## Verification (measured, this session)

```
Corpus after full Phase 2 reindex: 40 documents, 1895 chunks (1532 child / 363 parent)
Parser breakdown: 35 docling, 5 pypdf (fallback correctly triggered by the OCR timeout guard)

$ python scripts/run_eval.py --output baselines/phase2-v1.json
Loaded 22 golden-set items (20 answerable)
{
  "hit_rate@10": 1.0,
  "mrr": 0.975,
  "ndcg@10": 0.9815,
  "n_questions": 20
}
vs. baseline-v0 (Phase 1, dense-only): hit_rate@10 1.0, mrr 0.935, ndcg@10 0.9509
→ NDCG@10 and MRR both improved from sparse+RRF+rerank; hit_rate@10 was already
  perfect in Phase 1 and stayed perfect.

Filtering benchmark (backend/scripts/benchmark_filtering.py), real corpus,
document filter at 2.0% selectivity (30/1532 chunks):

  Natural plan (planner's own choice): Bitmap Heap Scan on ix_chunks_document_id
  + exact sort — HNSW never touched; GUCs irrelevant; avg_rows=10.0 throughout.

  Forced-HNSW plan (competing index dropped, enable_seqscan=off, both scoped
  to a rolled-back transaction): Index Scan using ix_chunks_embedding_hnsw.
    ef_search=10/40/80/160, iterative_scan=off:           avg_rows = 0.0 / 10  (bug reproduced)
    ef_search=10/40/80/160, iterative_scan=relaxed_order: avg_rows = 10.0 / 10 (fixed)
    latency cost of the fix: ~1-2ms -> ~4-6ms per query

Live end-to-end verification via /api/query:
  - Query rewrite: "What are its main limitations?" (session, prior turn about
    self-attention) -> rewritten to "What are the main limitations of
    self-attention in the Transformer?" — correct pronoun resolution.
  - Semantic cache: repeat of an identical question returned in 0.23s with
    cache_hit=true (vs. 200-580s for a fresh generation).
  - /api/retrieve confirmed all four score types populated per candidate
    (dense_score/rank, sparse_score/rank, rrf_score, rerank_score).

$ ruff check . / ruff format --check . / mypy app / pytest tests/unit -v
→ all clean; 27/27 tests passed (up from 19 in Phase 1).

Frontend: rebuilt (next build, includes TS type-check), HTTP-verified —
both / and /retrieval-inspector render 200 with expected content.

$ docker compose down && docker compose up -d
→ all 5 containers healthy; 40 documents / 1895 chunks / migration 0004
  survived the full cycle intact.
```

## Key decisions this phase

- **`tsv` as a DB-computed, GIN-indexed column** rather than maintaining a separate search-text field or triggering re-embeds for FTS — Postgres keeps it in sync automatically, and it composes cleanly with the existing chunk row.
- **RRF over a learned/weighted fusion** for combining dense and sparse — simple, robust, no extra training data or tuning needed, and it's what the Retrieval Inspector needs to show its work transparently.
- **Parent-child search-on-child/expand-to-parent** rather than embedding parents directly — children give tighter, more precise retrieval matches; parents give the generator enough surrounding context.
- **Semantic cache invalidated by a corpus-version counter, not TTL** — a stale cached answer against changed source material is worse than a cache miss; correctness over hit-rate.
- **`multiprocessing.Process` over `ThreadPoolExecutor` for the Docling timeout guard** — the only way to get a real, forcible kill on CPU-bound work in Python; verified live, not just reasoned about.
- **Forcing the HNSW query plan for the filtering benchmark, transparently** — rather than reporting "no bug found" (technically true but misses the point) or quietly assuming the naive script's numbers were meaningful, both the natural and forced plans are reported side by side in `DECISIONS.md` and this doc.

## What's next

**Phase 3 — Eval harness + CI gates**: grow the mini golden set (~20 items) to a full ~120-item golden set v1 with curation, add Ragas metrics + a custom LLM-judge, build an Evaluations page, formalize `baselines/baseline.json`, and wire deterministic-metric CI gates (`evals.yml`) so a PR that regresses retrieval fails automatically.
