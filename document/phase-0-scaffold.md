# Phase 0 — Scaffold

**Status:** complete
**Date:** 2026-07-30
**Spec reference:** `SPEC.md` §10 Phase 0
**Acceptance criteria:** `docker compose up` serves an empty API + blank frontend and CI is green.

## Goal

Stand up the monorepo skeleton for `ragforge` — a full Docker Compose stack (FastAPI backend, Next.js frontend, Postgres+pgvector, Redis, Celery worker), database migrations, and a CI pipeline — with nothing feature-complete yet, but every piece wired together and provably working before any real RAG logic is written.

## What was built

- **Repo root:** `SPEC.md` (verbatim build spec), `DECISIONS.md` (deviation log), `LICENSE` (MIT), `.gitignore`, `.env.example`, `document/` (this folder).
- **Backend** (`backend/`): FastAPI app factory (`app/main.py`) with `/api/health` and `/api/ready` (the latter checks live DB connectivity), a `pydantic-settings`-based `config.py` covering every tunable from `SPEC.md` §7.1 plus the latency-architecture settings from `implementation-plan.md` §2.E/§3.1 (`hnsw.iterative_scan`, `halfvec` storage, etc.), OTel SDK initialization, and the full module skeleton from `SPEC.md` §4 (`ingestion/`, `retrieval/`, `generation/`, `trust/`, `learning/`, `security/`, `evals/`, `observability/`, `providers/`, `models/`, `schemas/`, `db/`, `workers/`) — empty packages, ready for Phase 1+.
- **Alembic**, configured for async SQLAlchemy 2.0, with migration `0001` enabling the `vector` extension (pgvector pinned ≥0.8.2 per `DECISIONS.md`).
- **Celery worker** wired to Redis with a smoke-test `ping` task; real jobs (ingest/finetune/eval/redteam/monitor) land phase-by-phase.
- **Frontend** (`frontend/`): Next.js 16.2.12 (App Router) + React 19 + TypeScript + Tailwind, a single placeholder page, Dockerfile (multi-stage, standalone output).
- **`docker-compose.yml`**: `postgres` (`pgvector/pgvector:pg16`, explicit `shm_size: 1gb` to avoid the parallel-HNSW-build crash documented in `implementation-plan.md` §2.E7), `redis`, `api` (runs `alembic upgrade head` then `uvicorn`), `worker` (Celery), `frontend` — all with health checks and correct `depends_on` ordering.
- **CI** (`.github/workflows/ci.yml`): backend job (`ruff check`, `ruff format --check`, `mypy`, `pytest`) and frontend job (`eslint`, `tsc --noEmit`, `next build`).

## Key decisions made this phase

Full detail in `DECISIONS.md`; summary:
- Self-hosted-first provider layer (Ollama/bge-small/MiniLM default, optional free Gemini key for judge/enrichment only), $0/month free-tier cloud target, arXiv demo corpus, 8GB-CPU local profile — all carried over from `implementation-plan.md`.
- pgvector filtering/latency architecture (`hnsw.iterative_scan=relaxed_order`, `halfvec` storage, pgvector ≥0.8.2 pin) baked into `config.py` and `.env.example` from day one, not bolted on later.
- Next.js 16.2.12/React 19 instead of the spec's "14+" floor (already permitted, and current stable).
- Fixed a real ecosystem bug during verification: `eslint-config-next@16.2.12` no longer supports the `FlatCompat` bridge shown in older tutorials (it now exports a flat-config array directly) — caught because lint was actually run, not assumed to work.
- Accepted 12 non-blocking `npm audit` findings, all in vendored/dev tooling (Next's bundled `postcss`/`sharp`, `eslint-config-next`'s transitive `eslint` version) with no runtime exposure; documented for re-check at future phase closes.

## Verification (measured, this session)

```
$ docker compose up -d
 ... postgres Healthy, redis Healthy, api Started, worker Started, frontend Started

$ curl /api/health   → {"status":"ok"}
$ curl /api/ready    → {"status":"ok","database":true}
$ curl -I localhost:3000 → HTTP 200

$ psql -c "SELECT extname, extversion FROM pg_extension WHERE extname='vector';"
 vector | 0.8.4

$ psql -c "SELECT * FROM alembic_version;"
 0001

$ ruff check .        → All checks passed!
$ ruff format --check → 34 files already formatted
$ mypy app            → Success: no issues found in 27 source files
$ pytest tests/unit -v → 2 passed

$ npm run lint      → clean
$ npx tsc --noEmit  → exit 0
$ npm run build     → ✓ Compiled successfully, static pages generated
```

All five containers (`postgres`, `redis`, `api`, `worker`, `frontend`) run together via a single `docker compose up`; the API's `/ready` probe reflects true database connectivity (not a stub); the pgvector extension and the latency-architecture pin (≥0.8.2 — confirmed 0.8.4 installed) are live in the actual running database, not just documented.

## What's next

**Phase 1 — MVP vertical slice**: ingest arXiv PDFs through Docling, chunk, embed with `bge-small-en-v1.5`, dense-retrieve via pgvector, generate grounded/cited answers through Ollama, minimal Playground chat UI, OpenInference spans from day one, plus the mini golden set + `run_eval.py` that gives `baseline-v0` its first real numbers.
