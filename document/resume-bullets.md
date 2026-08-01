# Resume bullets — ragforge

Running log of quantified, ATS-keyword-rich bullets, updated at each phase close with real measured numbers (never invented ones). Draft phrasing now; tighten wording once the full project is done and a target job description is known.

---

## Project-level (draft — revisit after Phase 8 with final numbers)

- Built **ragforge**, a self-hosted Retrieval-Augmented Generation (RAG) platform with hybrid retrieval (dense + sparse + RRF fusion + cross-encoder reranking), per-claim citation verification, calibrated abstention, a CI-gated evaluation harness, an automated model fine-tuning/promotion flywheel, and a prompt-injection red-team suite — deployed via Docker Compose (local) and Cloud Run (public demo).
- Designed and measured a **pgvector filtering/latency architecture** (iterative-scan HNSW, partial indexes, `halfvec` quantization) via a controlled multi-configuration benchmark sweep, reproducing a documented pgvector failure mode and measuring the fix, rather than assuming vendor-claimed numbers. *(Numbers land at Phase 8 close.)*

## Phase 0 — Scaffold (2026-07-30)

- Stood up a production-shaped monorepo (FastAPI + Next.js/TypeScript + PostgreSQL/pgvector + Redis + Celery) with Docker Compose orchestration, Alembic migrations, and a GitHub Actions CI pipeline (lint, type-check, unit tests) passing from the first commit — establishing a verifiable, incremental build history rather than a single monolithic upload.

## Phase 1 — MVP vertical slice (2026-07-31)

- Built an end-to-end self-hosted RAG pipeline — Docling document parsing, `bge-small-en-v1.5` embeddings, PostgreSQL/pgvector (HNSW) dense retrieval, and a locally-hosted Qwen3-4B model (via Ollama) for grounded generation — and measured a **dense-only retrieval baseline of hit_rate@10 = 1.0, MRR = 0.935, NDCG@10 = 0.951** on a 40-document, 1,492-chunk corpus, establishing `baseline-v0` for every later retrieval improvement to be measured against.
- Designed a citation pipeline that parses per-claim source citations from free-text generation (rather than trusting constrained JSON-schema decoding, which measurably degraded a small local model's output quality) and filters out fabricated citation IDs against the real retrieved chunk set — a cheap integrity check ahead of full NLI-based claim verification.
- Diagnosed and fixed a citation-parsing bug via unit tests (not manual testing) that silently dropped valid citations under a specific sentence-boundary pattern, and a Celery/asyncio bug (per-task event loops vs. a shared connection pool) causing intermittent ingestion failures — both caught and resolved by building a real automated test suite and running the full pipeline against production-realistic data, not just inspecting the code.
- Automated demo-corpus construction by querying arXiv's API directly for real, current papers (rather than a hardcoded list), ingesting 40 LLM/RAG papers (707 pages) end-to-end with zero manual intervention.

## Phase 2 — Full retrieval engine (2026-08-01)

- Built a hybrid retrieval pipeline — Postgres full-text search fused with dense HNSW search via Reciprocal Rank Fusion, then cross-encoder reranking (MiniLM) — and measured a **+3.2 point NDCG@10 gain (0.951 → 0.982) and +4.0 point MRR gain (0.935 → 0.975) over the Phase 1 dense-only baseline**, with hit_rate@10 holding at a perfect 1.0, on the same 40-document corpus.
- Reproduced pgvector's documented filtered-search failure mode on real production data — not a synthetic benchmark — by using `EXPLAIN ANALYZE` to diagnose why the bug didn't initially appear (Postgres's own planner sidesteps the approximate HNSW index in favor of an exact scan below a size threshold), then forcing the approximate index path to demonstrate the bug (**0 of 10 requested rows returned** under `hnsw.iterative_scan=off`) and its fix (**10/10 reliably** under `relaxed_order`, at a measured ~3-4x but sub-10ms latency cost).
- Diagnosed and fixed a CPU-resource leak invisible to the task queue itself: a timeout guard around an unbounded third-party OCR call used a thread (unkillable in Python), which left runaway work consuming ~900% CPU indefinitely after the task it belonged to had already "succeeded" and moved on. Replaced it with a real child-process-based timeout that the OS can forcibly terminate, verified live via a CPU drop from ~800% to near-zero at the exact moment the fix took effect.
- Implemented parent-child hierarchical chunking (precise retrieval on child chunks, full context via parent expansion), session-aware conversational query rewriting, and a Redis-backed semantic cache with corpus-version invalidation (a cached answer can never outlive the source data it was computed against) — each verified against the live API, not just unit-tested in isolation.

---

*Keyword bank to weave in as features land: hybrid retrieval, RAG, vector database, HNSW, semantic caching, LLM evaluation, Ragas, LLM-as-judge, prompt injection defense, red-teaming, OpenTelemetry, distributed tracing, CI/CD regression gates, embedding fine-tuning, A/B testing, bootstrap confidence intervals, calibrated confidence scoring, FastAPI, Next.js, Docker, GCP Cloud Run.*
