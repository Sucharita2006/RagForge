# Resume bullets — ragforge

Running log of quantified, ATS-keyword-rich bullets, updated at each phase close with real measured numbers (never invented ones). Draft phrasing now; tighten wording once the full project is done and a target job description is known.

---

## Project-level (draft — revisit after Phase 8 with final numbers)

- Built **ragforge**, a self-hosted Retrieval-Augmented Generation (RAG) platform with hybrid retrieval (dense + sparse + RRF fusion + cross-encoder reranking), per-claim citation verification, calibrated abstention, a CI-gated evaluation harness, an automated model fine-tuning/promotion flywheel, and a prompt-injection red-team suite — deployed via Docker Compose (local) and Cloud Run (public demo).
- Designed and measured a **pgvector filtering/latency architecture** (iterative-scan HNSW, partial indexes, `halfvec` quantization) via a controlled multi-configuration benchmark sweep, reproducing a documented pgvector failure mode and measuring the fix, rather than assuming vendor-claimed numbers. *(Numbers land at Phase 8 close.)*

## Phase 0 — Scaffold (2026-07-30)

- Stood up a production-shaped monorepo (FastAPI + Next.js/TypeScript + PostgreSQL/pgvector + Redis + Celery) with Docker Compose orchestration, Alembic migrations, and a GitHub Actions CI pipeline (lint, type-check, unit tests) passing from the first commit — establishing a verifiable, incremental build history rather than a single monolithic upload.

---

*Keyword bank to weave in as features land: hybrid retrieval, RAG, vector database, HNSW, semantic caching, LLM evaluation, Ragas, LLM-as-judge, prompt injection defense, red-teaming, OpenTelemetry, distributed tracing, CI/CD regression gates, embedding fine-tuning, A/B testing, bootstrap confidence intervals, calibrated confidence scoring, FastAPI, Next.js, Docker, GCP Cloud Run.*
