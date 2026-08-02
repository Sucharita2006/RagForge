# ragforge

A self-hosted, trustworthy Retrieval-Augmented Generation (RAG) platform: upload documents, ask questions, get grounded answers with per-claim citations — plus a built-in evaluation harness, CI regression gates, and hybrid retrieval, all measured against a real corpus instead of assumed.

Built as a phase-by-phase engineering project. Every phase closes with a measured baseline, a written decision log, and a CI-gated regression check — see [`DECISIONS.md`](DECISIONS.md) for the full build log and [`SPEC.md`](SPEC.md) for the original design spec.

## What it does today

- **Hybrid retrieval**: dense (pgvector HNSW) + sparse (Postgres full-text) fused with Reciprocal Rank Fusion, then cross-encoder reranking (MiniLM), over parent-child hierarchical chunks.
- **Grounded generation**: local LLM (Qwen3-4B via Ollama) answers with per-sentence citations back to source chunks, with fabricated citation IDs filtered out.
- **Eval harness**: a curated 117-item golden set (single-hop / multi-hop / unanswerable / adversarial), retrieval + generation + LLM-as-judge metrics with bootstrap 95% confidence intervals, a persisted eval-run history, and an Evaluations UI.
- **CI regression gate**: `.github/workflows/evals.yml` ingests a fixture corpus and queries it end-to-end on every PR — a real retrieval regression fails the build automatically.
- **Session-aware querying**: conversational query rewriting and a Redis-backed semantic cache with corpus-version invalidation.

Everything runs self-hosted for $0 — no cloud API key required (see [Decisions](#why-self-hosted) below).

## Architecture

```
FastAPI (async) ─┬─ PostgreSQL 16 + pgvector (HNSW, halfvec)  — dense + sparse + full-text
                  ├─ Redis                                     — semantic cache + Celery broker
                  ├─ Celery worker                              — ingestion, eval runs
                  └─ Ollama (host)                               — local LLM generation + judging
Next.js (App Router, TypeScript) ── Evaluations UI, Retrieval Inspector, chat
```

| Layer | Choice |
|---|---|
| Backend | Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2.0 (async) + Alembic |
| Frontend | Next.js, TypeScript, Tailwind CSS |
| Database | PostgreSQL 16 + pgvector (HNSW, `halfvec` quantization) |
| Cache / queue | Redis + Celery |
| Generation / judge LLM | Qwen3-4B-Instruct via Ollama (self-hosted, CPU) |
| Embeddings | `BAAI/bge-small-en-v1.5` (384-dim) |
| Reranker | `cross-encoder/ms-marco-MiniLM-L-6-v2` |
| Document parsing | Docling (layout-aware), pypdf fallback |

## Measured results

Retrieval, on a 40-document / ~1,900-chunk arXiv corpus, hybrid pipeline (Phase 2 → Phase 3 baseline, 117-item golden set, bootstrap 95% CI):

| Metric | Value |
|---|---|
| hit_rate | 0.988 [0.964, 1.00] |
| MRR | 0.939 [0.894, 0.978] |
| NDCG@10 | 0.950 [0.913, 0.983] |
| answered-precision (calibrated abstention) | 1.00 [1.00, 1.00] |
| unanswerable-recall (correctly abstains) | 1.00 [1.00, 1.00] |

Full metrics, config, and the self-hosted-judge caveat are in [`baselines/baseline.json`](baselines/baseline.json). Every retrieval/generation change from here is measured as a delta against this baseline, gated in CI.

## Getting started

Requires Docker Desktop and [Ollama](https://ollama.com) running natively on the host (kept off Docker so its RAM footprint stays outside the WSL2/container memory cap).

```bash
ollama pull qwen3:4b-instruct
cp .env.example .env   # adjust if needed — defaults work out of the box
docker compose up -d
```

- API: `http://localhost:8000` (`/api/health`, `/api/ready`, OpenAPI docs at `/docs`)
- Frontend: `http://localhost:3000`
- Seed a demo corpus: `python scripts/seed_demo_corpus.py` (pulls real arXiv LLM/RAG papers)

## Project structure

```
backend/app/
  api/            REST endpoints (documents, query, retrieve, eval, ...)
  ingestion/      parsing (Docling), chunking, contextual enrichment
  retrieval/      dense/sparse/fusion/rerank pipeline, semantic cache
  generation/     citation-grounded answer generation
  evals/          golden-set runner, metrics, bootstrap CI, LLM judge
  providers/      swappable LLM/embedding/reranker interfaces
frontend/app/     Next.js routes (chat, Evaluations, Retrieval Inspector)
eval-datasets/    versioned golden sets (full / calibration / CI subset)
baselines/        stored metric baselines CI gates compare against
document/         per-phase build notes + resume bullets
```

## Why self-hosted?

The original spec assumed a free Gemini API key for generation, judging, and testset generation. This build instead defaults to a fully self-hosted, $0 stack (Ollama + local models for everything, including the LLM-as-judge), with every provider dependency-injected so a cloud model can be swapped in later without touching the harness. The real cost of that choice is measured, not hidden — see the `vs_spec_targets` block in `baselines/baseline.json` and [`DECISIONS.md`](DECISIONS.md) (2026-08-01 entries) for what that tradeoff actually does to judge-quality metrics.

## Build log

Each phase has a written summary with what was built, what changed from the original design and why, and measured verification numbers:

- [Phase 0 — Scaffold](document/phase-0-scaffold.md)
- [Phase 1 — MVP vertical slice](document/phase-1-mvp.md)
- [Phase 2 — Full retrieval engine](document/phase-2-retrieval.md)
- [Phase 3 — Eval harness + CI gates](document/phase-3-evals.md)

Full decision-by-decision engineering log: [`DECISIONS.md`](DECISIONS.md).

## Roadmap

Phase 4 (trust layer: per-claim NLI verification, calibrated confidence + abstention) onward — see [`SPEC.md`](SPEC.md) §10 and [`document/implementation-plan.md`](document/implementation-plan.md).

## License

See [`LICENSE`](LICENSE).
