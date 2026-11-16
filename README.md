# ragforge

A self-hosted, trustworthy Retrieval-Augmented Generation (RAG) platform: upload documents, ask questions, get grounded answers with per-claim citations — plus a built-in evaluation harness, public benchmarks and CI regression gates, all measured instead of assumed.

Built as a phase-by-phase engineering project. Every phase closes with a measured baseline, a written decision log, and a CI-gated regression check — see [`DECISIONS.md`](DECISIONS.md) for the full build log and [`SPEC.md`](SPEC.md) for the original design spec.

## What it does today

- **Retrieval with an abstaining reranker**: dense search (pgvector HNSW) over parent-child hierarchical chunks, then a cross-encoder (MiniLM) that moves up only the passages it is confident about and leaves the rest in retrieval order. BM25 keyword search fused by Reciprocal Rank Fusion is available but off by default, because it did not help where measured.
- **Grounded generation**: local LLM (Qwen3-4B via Ollama) answers with per-sentence citations back to source chunks, with fabricated citation IDs filtered out.
- **Eval harness**: a curated 117-item golden set (single-hop / multi-hop / unanswerable / adversarial), retrieval + generation + LLM-as-judge metrics with bootstrap 95% confidence intervals, a persisted eval-run history, and a Golden set page to read it.
- **Checked answers in the UI**: every answer sentence shows its verdict and links to the passage it was checked against; a withheld answer shows the sources it found instead.
- **Public benchmarks through the same harness**: BEIR SciDocs and ArguAna, full test splits, run by the project's own eval runner with each pipeline stage scored separately; plus SciFact's expert-labelled claims to test the answer checker.
- **CI regression gate**: `.github/workflows/evals.yml` ingests a fixture corpus and queries it end-to-end on every PR — a real retrieval regression fails the build automatically.
- **Session-aware querying**: conversational query rewriting and a Redis-backed semantic cache with corpus-version invalidation.

Everything runs self-hosted for $0 — no cloud API key required (see [Decisions](#why-self-hosted) below).

## Architecture

```
FastAPI (async) ─┬─ PostgreSQL 16 + pgvector (HNSW, halfvec)  — dense search, optional BM25
                  ├─ Redis                                     — semantic cache + Celery broker
                  ├─ Celery worker                              — ingestion, eval runs
                  └─ Ollama (host)                               — local LLM generation + judging
Next.js (App Router, TypeScript) ── Query · Inspect · Measure · Improve
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

### Public benchmarks

nDCG@10 on the full BEIR test splits, run by the project's own eval runner (`backend/scripts/beir.py`), with bootstrap 95% intervals. Published numbers are from the BEIR paper ([Thakur et al., 2021](https://arxiv.org/abs/2104.08663), Table 2) and the embedding model's card ([bge-small-en-v1.5](https://huggingface.co/BAAI/bge-small-en-v1.5)).

| | ArguAna (1,406 questions) | SciDocs (1,000 questions) |
|---|---|---|
| **ragforge** | **0.599** [0.579, 0.616] | **0.201** [0.186, 0.215] |
| ragforge before the reranker change | 0.432 | 0.182 |
| Best system in the BEIR paper | 0.493 (GenQ) | 0.166 (BM25 + MiniLM cross-encoder) |
| BM25, BEIR paper | 0.315 | 0.158 |
| bge-small-en-v1.5 alone, published | 0.596 | 0.205 |

ragforge beats every system in the BEIR paper on both sets. It matches its own embedding model's published scores rather than beating them: the gain came from no longer losing that score in later stages, which cost 0.17 on ArguAna. The reranker threshold was chosen on a fixed 30% of questions; on the other 70% the scores are 0.600 and 0.193. Its own golden set showed no significant change (nDCG@10 0.948 to 0.938, interval [-0.036, +0.012]). Method, stage-by-stage numbers and what was tried and dropped: [`DECISIONS.md`](DECISIONS.md) (2026-11-16).

### The answer checker on SciFact

Every answer sentence is checked against the passage it cites (MiniCheck, threshold 0.5). On SciFact's 323 expert-labelled (claim, abstract) pairs from the dev split:

| | Judged "supported" |
|---|---|
| Abstract supports the claim (138) | 55.8% [47.1, 64.5] |
| Abstract contradicts it (71) | 4.2% [0.0, 9.9] |
| Abstract says neither (114) | 0.9% [0.0, 2.6] |

When it says "supported" it is right 95% [90, 99] of the time (AUROC 0.90), but it misses 44% of claims that are supported. That strictness is the measured cause of the project's high unsupported-claim rate.

### Golden set

Retrieval, on a 40-document / ~1,900-chunk arXiv corpus (Phase 3 baseline, 117-item golden set, bootstrap 95% CI):

| Metric | Value |
|---|---|
| hit_rate | 0.988 [0.964, 1.00] |
| MRR | 0.939 [0.894, 0.978] |
| NDCG@10 | 0.950 [0.913, 0.983] |
| answered-precision (calibrated abstention) | 1.00 [1.00, 1.00] |
| unanswerable-recall (correctly abstains) | 1.00 [1.00, 1.00] |

Full metrics, config, and the self-hosted-judge caveat are in [`baselines/baseline.json`](baselines/baseline.json). `python scripts/seed_demo_corpus.py --from-golden-set` rebuilds the exact paper versions this set was written against.

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
- With an NVIDIA GPU: `docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d` runs the embedder, reranker and claim checker on it (CUDA 13 driver, about 3GB more to download). Answers are the same; only speed changes.

## Project structure

```
backend/app/
  api/            REST endpoints (documents, query, retrieve, eval, ...)
  ingestion/      parsing (Docling), chunking, contextual enrichment
  retrieval/      dense/sparse/fusion/rerank pipeline, semantic cache
  generation/     citation-grounded answer generation
  evals/          golden-set runner, metrics, bootstrap CI, LLM judge
  providers/      swappable LLM/embedding/reranker interfaces
frontend/app/     Next.js routes: Query (/); Inspect: Candidates, Timeline;
                  Measure: Golden set, A/B, Metrics; Improve: Feedback loop, Trust settings
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
- [Phase 4 — Trust layer](document/phase-4-trust.md)
- [Phase 5 — Observability](document/phase-5-observability.md)
- [Phase 6 — Learning flywheel](document/phase-6-learning.md)

Full decision-by-decision engineering log: [`DECISIONS.md`](DECISIONS.md).

## Roadmap

- **Calibrate the claim checker's threshold**: SciFact shows MiniCheck at 0.5 is right when it says "supported" but misses 44% of supported claims; choose the threshold on SciFact's train split and confirm on dev.
- **Phase 7, red-teaming**: the attack-success-rate target is still unmeasured (see [`SPEC.md`](SPEC.md) §10 and [`document/implementation-plan.md`](document/implementation-plan.md)).

## License

See [`LICENSE`](LICENSE).
