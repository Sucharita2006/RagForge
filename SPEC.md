# ragforge — Complete Build Specification

**Project:** ragforge — a trustworthy, self-improving RAG platform with a built-in evaluation, observability, and security layer.

**One-liner:** A document Q&A system that verifies every claim it makes against source spans, abstains with a calibrated confidence score when context is insufficient, retrains its own retriever/reranker from user feedback, and is continuously red-teamed against prompt-injection attacks — with full distributed tracing and a CI-gated evaluation harness.

> **Note:** This is the original build spec as produced by deep research. It is kept verbatim as the source of truth for scope/features. All amendments, corrections, and deviations (self-hosted model swap, $0 cloud budget, latency architecture, etc.) are tracked separately in `DECISIONS.md` and `document/implementation-plan.md` — read those alongside this file, since several defaults below (e.g. Gemini-only, Cloud SQL) have been superseded.

---

## 0. How to use this document (instructions for the coding agent)

1. This file is the single source of truth. Keep it at the repo root as `SPEC.md`.
2. Build strictly in the phase order of **Section 10**. Do not start a phase until the previous phase's acceptance criteria pass.
3. Rules for every task:
   - Write tests alongside features (pytest for backend). A feature is done only when its tests pass.
   - Every retrieval/generation step MUST emit an OpenInference-convention OpenTelemetry span (see Section 3.8).
   - All configuration via environment variables / `config.py` (pydantic-settings). Never hardcode secrets, model names, or thresholds.
   - Small, focused commits with conventional-commit messages (`feat:`, `fix:`, `test:`, `chore:`).
   - Type-annotate all Python functions. Use Pydantic v2 models for all API request/response schemas.
   - If a library choice in this spec fails/conflicts, prefer the simplest working alternative and record the decision in `DECISIONS.md`.
4. The quality targets in Section 7 are hard gates — the CI eval workflow must fail when they regress.

## 1. Project overview

### 1.1 What it is
A self-hostable, full-stack RAG (Retrieval-Augmented Generation) platform: users upload documents, ask questions, and get grounded answers with per-claim citations. Unlike standard RAG apps, ragforge closes four loops:

1. **Verify** — every generated sentence is checked against retrieved source spans by an NLI claim-verification model; the UI highlights each claim as supported / unsupported with clickable citations.
2. **Abstain** — a calibrated confidence score decides whether to answer or say "I don't have enough information," trading coverage for precision.
3. **Learn** — thumbs-down feedback and retrieval failures are mined into hard negatives; the embedder and cross-encoder reranker are periodically fine-tuned and only promoted if an A/B test shows a statistically significant improvement.
4. **Defend** — an automated red-team harness attacks the system with poisoned documents (indirect prompt injection) and reports attack success rate before/after defenses.

Plus the platform layer: hybrid retrieval (dense + sparse + RRF fusion + reranking), OpenTelemetry/OpenInference distributed tracing with a custom trace viewer, a Ragas-based eval harness with a versioned golden dataset, CI regression gates, and A/B experiment comparison.

### 1.2 Non-goals
- No model training from scratch (only fine-tuning small embedding/reranker models).
- No multi-tenancy/auth beyond a single demo API key (stretch only).
- No support for every file format — PDF, DOCX, HTML, TXT, MD is enough.
- No Kubernetes — Docker Compose locally, Cloud Run in production.

### 1.3 Deployment targets (both required)
- **Local self-host:** `docker compose up` brings up the entire stack (API, frontend, Postgres+pgvector, Redis, worker).
- **Cloud demo:** same containers deployed to GCP Cloud Run (API + frontend), Cloud SQL for Postgres+pgvector, GCS for raw document blobs, Secret Manager for keys. Long-running jobs (ingestion, fine-tuning, red-team, evals) run as Cloud Run Jobs triggered via API/Cloud Scheduler instead of an always-on Celery worker.

## 2. Tech stack (locked decisions)

| Layer | Choice | Notes |
|---|---|---|
| Backend | Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2.0 + Alembic, uvicorn | async endpoints |
| Frontend | Next.js 14+ (App Router), TypeScript, Tailwind CSS | single frontend app, calls REST API |
| Database | PostgreSQL 16 + pgvector ≥ 0.7 | HNSW index for dense vectors |
| Sparse retrieval | Postgres full-text search (tsvector + websearch_to_tsquery, ts_rank_cd) | no Elasticsearch; one DB for everything |
| Cache / queue | Redis 7 | semantic cache + job broker (local) |
| Background jobs | Celery (local via compose); Cloud Run Jobs in prod | ingestion, fine-tune, evals, red-team |
| Generation LLM | Gemini 2.5 Flash default; Gemini 2.5 Pro for LLM-as-judge | via `google-genai` SDK; model names in env |
| Embeddings (default) | `gemini-embedding-001`, truncated to **768 dims** (Matryoshka) | API-based; near-zero ops |
| Embeddings (alt, swappable) | `BAAI/bge-m3` via sentence-transformers | self-hosted option behind `EmbeddingProvider` interface; used in dev benchmarks + fine-tuning |
| Reranker | `BAAI/bge-reranker-v2-m3` (CPU, self-hosted default) | optional providers: Cohere Rerank API, `answerai-colbert-small-v1` late-interaction mode — all behind `RerankerProvider` interface |
| Claim verification | MiniCheck `lytang/MiniCheck-Flan-T5-Large` (CPU-friendly) | per-sentence entailment vs retrieved spans |
| Document parsing | Docling (primary: PDF/DOCX/HTML, layout + tables + OCR); fallback pypdf for simple digital PDFs | parser choice recorded per document |
| Chunking | recursive token splitter (default) + parent-child hierarchical; contextual chunk prefix generated by Gemini Flash | see Section 7 parameters |
| Eval framework | Ragas (metrics + synthetic testset generation) + custom LLM-as-judge; pytest-based CI gates | judge = Gemini 2.5 Pro with position randomization |
| Fine-tuning | sentence-transformers v3: `MultipleNegativesRankingLoss` + `MatryoshkaLoss` for embedder; `CrossEncoderTrainer` for reranker; `mine_hard_negatives` util | runs as background job; GPU optional (Colab/local) |
| Tracing | OpenTelemetry SDK + OpenInference semantic conventions; spans persisted to Postgres | custom Next.js trace viewer (no external APM) |
| Metrics/analytics | computed from spans table (cost, latency, tokens, cache hits) | custom dashboard |
| Red-team | custom harness + payload corpus in `redteam/payloads/`; canary-token assertions | ASR report persisted |
| Load testing | k6 (scripts in `loadtest/`) | run manually, results in README |
| Containers | Docker + docker-compose | multi-stage builds |
| Cloud | GCP: Cloud Run (svc: api, frontend; jobs: worker tasks), Cloud SQL (Postgres), GCS, Secret Manager, Artifact Registry | region: asia-south1 |
| CI/CD | GitHub Actions: `ci.yml` (lint+unit+integration), `evals.yml` (regression gates), `deploy.yml` | see Section 8.7 |
| Lint/format | ruff (lint+format), mypy (loose), eslint + prettier | pre-commit optional |

## 3. Feature specification

### 3.1 Ingestion pipeline
- Upload via multipart file(s) or URL. Raw file stored (local volume / GCS). Job enqueued; status pollable.
- Parse with Docling → structured elements (headings, paragraphs, tables, page numbers). Store parser metadata.
- **Chunking:** recursive splitter at `CHUNK_SIZE=512` tokens, `CHUNK_OVERLAP=64`, respecting element boundaries where possible. Also create **parent chunks** (`PARENT_CHUNK_SIZE=2048`) and link `chunk.parent_id`.
- **Contextual enrichment:** for each child chunk, call Gemini Flash with the parent/document context to generate a ≤100-token situating prefix ("This chunk is from <doc>, section <X>, and discusses ..."). Store as `context_prefix`; the embedded text = `context_prefix + "\n" + content`. Feature-flag: `CONTEXTUAL_ENRICHMENT=true`.
- Compute `content_hash` (sha256 of normalized content). **Incremental re-ingestion:** re-uploading a document re-embeds only chunks whose hash changed; unchanged chunks are reused.
- Embed via active `EmbeddingProvider` (records `embedding_model`, `dim` per chunk). Populate `tsv` column for FTS.
- **Ingest-time security scan:** run injection-pattern classifier (Section 3.6) on each chunk; flag suspicious chunks (`quarantined=true`, excluded from retrieval by default, visible in UI for review).

### 3.2 Retrieval engine
Pipeline per query (each step = one span):
1. **Query processing:** conversational rewrite (resolve pronouns using chat history) via Gemini Flash. Optional `HYDE=true` and `MULTI_QUERY_N` fan-out (default off in prod, available in experiments).
2. **Semantic cache check:** embed query; if cosine sim ≥ `SEMANTIC_CACHE_THRESHOLD=0.92` against cached (query, answer, corpus_version) entries in Redis → return cached answer (marked `cache_hit=true`). TTL 24h; invalidate on corpus change.
3. **Dense search:** pgvector HNSW cosine, top `DENSE_TOP_K=50`, with optional metadata filters (document_ids, date range, tags).
4. **Sparse search:** Postgres FTS, top `SPARSE_TOP_K=50`.
5. **Fusion:** Reciprocal Rank Fusion, `RRF_K=60`. Deduplicate by chunk id.
6. **Rerank:** cross-encoder over top `RERANK_CANDIDATES=50` fused results → keep `FINAL_TOP_K=8`.
7. **Context assembly:** replace child chunks with parent chunks where beneficial (dedupe overlapping parents); reorder so highest-scored chunks are at the beginning and end of the context (lost-in-the-middle mitigation); enforce `MAX_CONTEXT_TOKENS=6000`.
- Debug endpoint `POST /api/retrieve` returns every candidate with dense score, sparse rank, RRF score, rerank score — powers the Retrieval Inspector page.

### 3.3 Generation
- Grounded prompt: system rules = answer ONLY from provided context; cite chunk ids per sentence; if insufficient, say so. Retrieved content is wrapped in delimiters and explicitly labeled as untrusted data (spotlighting — Section 3.6).
- Structured output (JSON schema): `{"answer_sentences": [{"text": str, "citations": [chunk_id,...]}], "insufficient_context": bool}`. Temperature 0.1.
- Streaming variant via SSE for the chat UI (stream text, then send final structured claims + trust payload as a terminal event).

### 3.4 Trust layer (differentiator #1)
- **Claim splitting:** each answer sentence = one claim (from structured output).
- **Claim verification:** for each claim, run MiniCheck against the union of its cited chunks (fallback: all retrieved chunks). Store per-claim `support_prob`; verdict `supported` if ≥ `MINICHECK_SUPPORT_THRESHOLD=0.5`, else `unsupported`.
- **Confidence score (0–1):** weighted combination — mean claim support (0.5), retrieval strength (0.3: normalized mean rerank score of used chunks), generator sufficiency signal (0.2: `insufficient_context=false` and judge-free heuristics). Weights in config.
- **Selective answering:** if confidence < `ABSTAIN_THRESHOLD` → return abstention response ("I don't have enough grounded information...") with the top sources it *did* find. Threshold is **calibrated** (Section 8.5) on a calibration split to hit ≥90% precision on answered questions; expose a coverage↔precision slider in Settings that shows the calibration curve.
- **UI:** per-claim highlighting (green=supported, amber=unsupported) with hover → source span; answer-level confidence badge; abstention state styled distinctly.

### 3.5 Learning flywheel (differentiator #2)
- **Feedback capture:** thumbs up/down + optional free-text correction per answer (`POST /api/feedback`). Store with full trace linkage.
- **Hard-negative mining:** nightly job — for thumbs-down answers and eval failures, collect (query, high-ranked-but-wrong chunks) as hard negatives; also use `mine_hard_negatives` over the corpus for synthetic pairs.
- **Synthetic training data:** script generates (query → gold chunk) pairs from the corpus with Gemini Flash (`scripts/generate_training_pairs.py`), filtered by a round-trip retrieval check.
- **Fine-tune jobs:** (a) embedder: fine-tune bge-m3 (or distil variant) with MNRL + MatryoshkaLoss; (b) reranker: fine-tune bge-reranker-v2-m3 with mined hard negatives. Each run logged to `model_registry` with eval metrics.
- **A/B promotion gate:** run golden-set eval with candidate vs current model; compute bootstrap 95% CI on ΔNDCG@10 and Δhit-rate; **promote only if CI excludes 0** (`POST /api/models/{id}/promote` enforces this). Active models are hot-swappable via registry pointer; embedder swap triggers re-embed job.

### 3.6 Security layer (differentiator #3)
- **Threat model:** indirect prompt injection via poisoned uploaded documents.
- **Defenses (all feature-flagged):**
  1. Ingest-time sanitizer: strip hidden text (white-font spans, HTML comments, zero-width chars); regex + small-LLM classifier flags instruction-like content ("ignore previous instructions", "system:", exfil URLs) → quarantine chunk.
  2. Spotlighting at generation: retrieved content wrapped in `<retrieved_data>` delimiters + explicit system rule that content inside is data, never instructions.
  3. Output guard: responses scanned for canary tokens and attacker-controlled URLs/markdown-image exfil patterns before returning.
- **Red-team harness:** `redteam/` contains ≥60 attack documents across categories: direct injection, role hijack, hidden-text injection, markdown/link exfiltration, canary-exfil bait, multilingual payloads, split/chained attacks. Runner ingests attack docs into an isolated corpus, fires the paired trigger queries, asserts canary token / attack marker absent from output, computes **Attack Success Rate (ASR)** per category, persists a report. `POST /api/redteam/run` + report page in UI.

### 3.7 Evaluation harness
- **Golden dataset** (Section 8.3): versioned JSONL in `eval-datasets/`, generated with Ragas TestsetGenerator + manual curation; includes answerable (single-hop, multi-hop), **unanswerable** (must abstain), and adversarial items.
- **Metrics computed per run:** retrieval — hit_rate@k, MRR, NDCG@10, context_precision, context_recall; generation — faithfulness, answer_relevancy, answer_correctness (vs ground truth); trust — unsupported_claim_rate, abstention_precision/recall on unanswerable set, answered-precision & coverage; cost/latency percentiles.
- **LLM-as-judge:** Gemini 2.5 Pro, pointwise rubric prompts; candidate order/position randomized; 20-sample human-calibration spot-check stored with agreement stats.
- **Experiments:** an experiment = named config bundle (embedding model, chunk size, reranker on/off, top-k, RRF k, enrichment on/off...). `POST /api/eval/run` executes dataset × config; comparison view shows metric deltas **with bootstrap 95% CIs**.
- **CI regression gates:** Section 8.7.

### 3.8 Observability
- OpenInference span kinds: `CHAIN` (request root), `RETRIEVER` (with `document.id`/`document.score` per candidate), `RERANKER` (input/output docs, top_k, model), `LLM` (model, token counts, cost), `GUARDRAIL` (sanitizer/output guard), `EVALUATOR` (claim verification, judge calls), `EMBEDDING`.
- Every span records latency; LLM/embedding spans record input/output tokens and computed cost (price table in config). Spans persisted to Postgres (`spans` table) via OTel exporter.
- **Trace viewer page:** waterfall per query — step durations, token/cost per span, retrieved chunks with scores, claim verdicts.
- **Analytics page:** p50/p95 latency, cost/query, cache hit rate, QPS, abstention rate, feedback ratio — over time windows.
- Online monitoring: nightly job scores a sample of production queries for faithfulness (judge) → time-series on the eval dashboard; alert log entry if 7-day faithfulness drops >5 points.

### 3.9 Frontend pages (Next.js)
1. **Playground** — chat with streaming, per-claim highlight + citations drawer, confidence badge, abstention state, feedback buttons.
2. **Documents** — upload, job status, parser/chunk stats, quarantined-chunk review.
3. **Retrieval Inspector** — query box → table of candidates with dense/sparse/RRF/rerank scores, chunk preview, parent toggle.
4. **Evaluations** — runs list, metric cards, trend charts, per-question drill-down (query → retrieved → answer → claim verdicts → judge notes).
5. **Experiments** — side-by-side config comparison with deltas + CIs.
6. **Traces** — searchable list + waterfall detail view.
7. **Analytics** — cost/latency/cache/abstention dashboards.
8. **Learning** — feedback list, failure clusters (retrieval-miss / generation-error / parsing-gap / knowledge-gap), model registry with promote button + A/B report.
9. **Security** — red-team runs, ASR by category, before/after defense comparison.
10. **Settings** — config viewer, abstention coverage↔precision slider with calibration curve.

## 4. Repository structure (monorepo)

```
ragforge/
├── SPEC.md                          # this file
├── DECISIONS.md                     # agent-recorded deviations/decisions
├── README.md                        # architecture diagram + benchmark table (Section 11)
├── docker-compose.yml               # api, frontend, postgres(pgvector), redis, worker
├── .env.example
├── .github/workflows/
│   ├── ci.yml                       # lint + unit + integration
│   ├── evals.yml                    # regression gates (PR + nightly)
│   └── deploy.yml                   # build → Artifact Registry → Cloud Run
├── backend/
│   ├── Dockerfile
│   ├── pyproject.toml
│   ├── alembic/                     # migrations
│   ├── app/
│   │   ├── main.py                  # FastAPI app factory, OTel init
│   │   ├── config.py                # pydantic-settings (all Section 7 params)
│   │   ├── api/                     # routers: ingest, documents, query, retrieve,
│   │   │                            #   feedback, traces, eval, experiments, models,
│   │   │                            #   redteam, failures, analytics, settings
│   │   ├── ingestion/               # parsers.py, chunkers.py, enrich.py, hashing.py, pipeline.py
│   │   ├── retrieval/               # dense.py, sparse.py, fusion.py (RRF), rerankers/,
│   │   │                            #   query_transform.py, assembly.py, cache.py
│   │   ├── generation/              # prompts.py, generator.py, streaming.py, schemas.py
│   │   ├── trust/                   # claims.py, minicheck.py, confidence.py, abstain.py, calibration.py
│   │   ├── learning/                # feedback.py, mining.py, synth_pairs.py,
│   │   │                            #   finetune_embedder.py, finetune_reranker.py,
│   │   │                            #   registry.py, ab_gate.py, failure_clustering.py
│   │   ├── security/                # sanitizer.py, spotlight.py, output_guard.py, redteam_runner.py
│   │   ├── evals/                   # ragas_runner.py, judge.py, metrics.py, datasets.py, online_monitor.py
│   │   ├── observability/           # otel.py, openinference.py, cost.py, spans_store.py
│   │   ├── providers/               # embeddings/ (gemini.py, bge_m3.py, base.py),
│   │   │                            #   llm/ (gemini.py, base.py)
│   │   ├── models/                  # SQLAlchemy models (Section 5)
│   │   ├── schemas/                 # Pydantic API schemas
│   │   ├── db/                      # session.py
│   │   └── workers/                 # celery_app.py, tasks.py (ingest, finetune, eval, redteam, monitor)
│   └── tests/
│       ├── unit/            ├── integration/
│       ├── evals/           └── conftest.py  (test corpus fixtures)
├── frontend/
│   ├── Dockerfile
│   ├── package.json
│   ├── app/                         # routes per Section 3.9
│   ├── components/                  # ClaimHighlight, ConfidenceBadge, ScoreTable,
│   │                                #   TraceWaterfall, MetricCard, DeltaCompare, ...
│   └── lib/                         # api client, types, sse.ts
├── eval-datasets/
│   ├── v1/golden.jsonl              # full 200-item set
│   ├── v1/ci_split.jsonl            # 50-item fast CI subset
│   └── v1/calibration.jsonl         # 60-item calibration split
├── redteam/payloads/                # attack docs by category + triggers.yaml
├── scripts/                         # seed_demo_corpus.py, generate_training_pairs.py,
│                                    #   run_eval.py, run_redteam.py, export_baseline.py
├── baselines/baseline.json          # stored main-branch metric baseline for CI gates
└── loadtest/query_test.js           # k6
```

## 5. Data model (Postgres — key tables/columns)

| Table | Key columns |
|---|---|
| documents | id, filename, source_url, mime, parser, status, gcs_path, created_at, corpus_version |
| chunks | id, document_id, parent_id (nullable), content, context_prefix, token_count, page, section_path, metadata jsonb, content_hash, quarantined bool, tsv tsvector, embedding vector(768), embedding_model, created_at |
| queries | id, session_id, raw_text, rewritten_text, filters jsonb, cache_hit bool, trace_id, created_at |
| answers | id, query_id, text, claims jsonb `[{text, citations:[chunk_id], support_prob, verdict}]`, confidence float, abstained bool, model, prompt_version, input_tokens, output_tokens, cost_usd, latency_ms |
| feedback | id, answer_id, rating (+1/-1), correction text, created_at |
| spans | id, trace_id, parent_span_id, kind, name, start/end, latency_ms, attributes jsonb (tokens, cost, doc ids/scores), status |
| eval_datasets | id, version, path, size, composition jsonb |
| eval_runs | id, dataset_version, config jsonb, git_sha, started/finished, status |
| eval_results | id, run_id, question_id, metrics jsonb, retrieved jsonb, answer jsonb, judge_notes |
| experiments | id, name, config_a jsonb, config_b jsonb, run_a_id, run_b_id, deltas jsonb (with CIs) |
| model_registry | id, kind (embedder/reranker), base_model, artifact_path, train_config jsonb, eval_metrics jsonb, status (candidate/active/retired), promoted_at |
| training_pairs | id, query, positive_chunk_id, hard_negative_chunk_ids jsonb, source (feedback/synthetic/mined), created_at |
| redteam_runs | id, started_at, defenses jsonb, asr_overall, asr_by_category jsonb, report jsonb |
| failure_clusters | id, window, cluster_label (retrieval_miss/generation_error/parsing_gap/knowledge_gap), size, sample_query_ids jsonb, suggested_action |

Indexes: HNSW on chunks.embedding (`m=16, ef_construction=200`); GIN on chunks.tsv; btree on all FKs; spans(trace_id).

## 6. API surface (REST, `/api` prefix)

| Method & path | Purpose |
|---|---|
| POST /ingest · GET /ingest/{job_id} | upload files/URL → job; poll status |
| GET /documents · DELETE /documents/{id} · POST /documents/{id}/reindex | manage corpus |
| POST /query | question → {answer, claims[], confidence, abstained, citations, trace_id, cache_hit} |
| POST /query/stream | SSE: tokens → terminal trust payload |
| POST /retrieve | debug: all candidates with dense/sparse/RRF/rerank scores |
| POST /feedback | rating + optional correction |
| GET /traces · GET /traces/{trace_id} | list/detail spans |
| POST /eval/run · GET /eval/runs · GET /eval/runs/{id} | execute + inspect eval runs |
| GET/POST /experiments · GET /experiments/{id} | A/B config comparisons |
| POST /finetune/embedder · POST /finetune/reranker | launch training jobs |
| GET /models · POST /models/{id}/promote | registry; promote enforces A/B significance gate |
| POST /redteam/run · GET /redteam/reports/{id} | security harness |
| GET /failures/clusters · GET /gaps | failure clustering + knowledge-gap analytics |
| GET /analytics/summary | latency/cost/cache/abstention time series |
| GET /settings · PATCH /settings/abstain-threshold | config view; calibrated slider |
| GET /health · GET /ready | probes |

## 7. Accuracy parameters, defaults, and quality gates

### 7.1 Tunable defaults (env / config.py)
| Parameter | Default | Notes |
|---|---|---|
| CHUNK_SIZE / CHUNK_OVERLAP | 512 / 64 tokens | recursive splitter |
| PARENT_CHUNK_SIZE | 2048 tokens | parent-child retrieval |
| CONTEXTUAL_ENRICHMENT | true | ≤100-token Gemini Flash prefix |
| EMBEDDING_MODEL / EMBEDDING_DIM | gemini-embedding-001 / 768 | Matryoshka truncation |
| DENSE_TOP_K / SPARSE_TOP_K | 50 / 50 | |
| RRF_K | 60 | fusion constant |
| RERANK_CANDIDATES / FINAL_TOP_K | 50 / 8 | cross-encoder stage |
| MAX_CONTEXT_TOKENS | 6000 | after parent expansion + reorder |
| HNSW m / ef_construction / ef_search | 16 / 200 / 80 | pgvector |
| SEMANTIC_CACHE_THRESHOLD / TTL | 0.92 / 24h | Redis |
| GEN_TEMPERATURE / MAX_OUTPUT_TOKENS | 0.1 / 1024 | |
| MINICHECK_SUPPORT_THRESHOLD | 0.5 | claim supported if ≥ |
| CONFIDENCE_WEIGHTS | 0.5 / 0.3 / 0.2 | claim-support / retrieval / sufficiency |
| ABSTAIN_THRESHOLD | calibrated (init 0.55) | set by calibration job targeting ≥0.90 answered-precision |
| HYDE / MULTI_QUERY_N | false / 0 | experiment-only by default |

### 7.2 Quality targets & CI gates (golden set v1, full 200 items)
| Metric | Target | CI regression rule (vs `baselines/baseline.json`) |
|---|---|---|
| hit_rate@8 | ≥ 0.85 | fail if ↓ > 0.03 |
| NDCG@10 | ≥ 0.75 | fail if ↓ > 0.03 |
| context_recall | ≥ 0.75 | fail if ↓ > 0.03 |
| context_precision | ≥ 0.70 | fail if ↓ > 0.03 |
| faithfulness | ≥ 0.85 | fail if ↓ > 0.02 |
| answer_correctness | ≥ 0.75 | fail if ↓ > 0.03 |
| unsupported_claim_rate | ≤ 0.05 | fail if ↑ > 0.02 |
| abstention on unanswerable subset | ≥ 0.80 recall | fail if ↓ > 0.05 |
| answered-precision (calibrated) | ≥ 0.90 | report coverage alongside |
| confidence calibration ECE | ≤ 0.10 | report reliability diagram |
| red-team ASR (defenses on) | ≤ 0.10 (goal 0) | fail if ↑ vs baseline |
| p95 end-to-end latency (uncached) | ≤ 3.0 s | report; gate in load test only |
| p95 cached / first streamed token | ≤ 300 ms / ≤ 1.5 s | report |

Every improvement must be reported as a **delta vs the dense-only Phase-1 baseline** (keep that config runnable forever as experiment `baseline-v0`).

## 8. Testing & evaluation strategy

### 8.1 Test pyramid
- **Unit (fast, mocked LLMs):** chunking boundaries, `content_hash` incremental logic, RRF math (known-input assertion), score normalization, confidence formula, abstention decision, sanitizer regexes (positive+negative cases), cost calculator, span emission (assert every pipeline step produces the expected span kind).
- **Integration (compose services up, tiny local models, ≤10-doc corpus fixture):** ingest→retrieve→generate happy path; `/retrieve` returns all four score types; abstention triggers on an out-of-corpus question; citations reference real chunk ids; incremental re-ingest re-embeds only changed chunks; feedback persists + links to trace.
- **Eval (offline, on `ci_split.jsonl`):** metric computation + gate logic; runs in CI.
- **Contract:** frontend API client typed against backend Pydantic schemas (generate `openapi.json`; check in CI).

### 8.2 Golden-set-driven correctness
- The eval harness is the primary correctness signal for RAG behavior; unit tests cover the deterministic plumbing.
- Store `baselines/baseline.json` (metrics on `main`); `evals.yml` compares PR metrics to it using Section 7.2 rules.

### 8.3 Golden dataset construction
- Generate with Ragas `TestsetGenerator` over the demo corpus (single-hop specific, multi-hop abstract, multi-hop specific synthesizers) → human-curate.
- Composition (v1, 200 items): 90 single-hop answerable, 50 multi-hop answerable, 40 unanswerable (correct behavior = abstain), 20 adversarial/injection-adjacent.
- Split: 200 full · 60 calibration · 50 fast CI subset. Version the folder; bump on change.

### 8.4 LLM-as-judge protocol
- Judge = Gemini 2.5 Pro; pointwise rubric (0–1) for faithfulness/answer_correctness with explicit criteria + few-shot anchors.
- Bias mitigation: randomize any candidate ordering; strip model identifiers; log raw judge rationale.
- Calibration: 20 human-labeled items per release; report judge–human agreement (Cohen's κ); recalibrate rubric if divergence > 20%.

### 8.5 Confidence calibration
- Fit `ABSTAIN_THRESHOLD` on `calibration.jsonl`: sweep thresholds, plot coverage vs answered-precision, pick lowest threshold meeting ≥0.90 precision; persist curve for the Settings slider.
- Report ECE + reliability diagram; recalibrate whenever an embedder/reranker is promoted.

### 8.6 Security testing
- Red-team runner computes ASR overall + per category on the payload corpus; a build **fails** if ASR with defenses on exceeds the stored baseline.
- Include canary-token exfil tests (assert canary never appears in output) and a hidden-text extraction unit test.

### 8.7 CI/CD workflows
- **ci.yml** (every PR): ruff + mypy + eslint/prettier; backend unit + integration (compose); build openapi + type-check frontend client. Must pass to merge.
- **evals.yml** (PR label `run-evals` + nightly): eval on `ci_split` (PR) / full set (nightly) → apply Section 7.2 gates → post metric table + deltas as PR comment; nightly also runs online-monitor + red-team and updates trend charts.
- **deploy.yml** (merge to main): build multi-arch images → Artifact Registry → deploy `api` + `frontend` to Cloud Run, run Alembic migrations as a Cloud Run Job, register worker task jobs. Smoke-test `/ready` post-deploy.

## 9. Configuration & environment (`.env.example` keys)
`DATABASE_URL, REDIS_URL, GCP_PROJECT, GCP_REGION, GCS_BUCKET, GOOGLE_API_KEY (or Vertex ADC), GEN_MODEL=gemini-2.5-flash, JUDGE_MODEL=gemini-2.5-pro, EMBEDDING_PROVIDER=gemini, EMBEDDING_MODEL=gemini-embedding-001, EMBEDDING_DIM=768, RERANKER_PROVIDER=bge, RERANKER_MODEL=BAAI/bge-reranker-v2-m3, MINICHECK_MODEL=lytang/MiniCheck-Flan-T5-Large, OTEL_EXPORTER=postgres, API_KEY (demo auth), all Section 7.1 tunables.`
Provide both a Gemini-API-key path (local/dev) and a Vertex AI ADC path (Cloud Run) in the LLM/embedding providers.

## 10. Phased build plan (execute in order)

**Phase 0 — Scaffold.** Monorepo, docker-compose (api+frontend+postgres/pgvector+redis+worker), config.py, health/ready, Alembic init, CI lint/unit skeleton, `DECISIONS.md`. *Done when:* `docker compose up` serves an empty API + blank frontend and CI is green.

**Phase 1 — MVP vertical slice (dense-only baseline).** Ingest one PDF (Docling → recursive chunks → Gemini embeddings → pgvector) → dense retrieve → grounded Gemini generation with citations → minimal Playground chat. Emit OpenInference spans from day one. Seed demo corpus. *Done when:* an end-to-end cited answer works and this exact config is saved as experiment `baseline-v0`.

**Phase 2 — Full retrieval engine.** Add sparse FTS + RRF fusion + cross-encoder reranking + parent-child chunking + contextual enrichment + query rewrite + semantic cache + lost-in-the-middle reorder + incremental re-ingest. Build Retrieval Inspector page. *Done when:* `/retrieve` shows all four score types and NDCG@10 beats `baseline-v0` on `ci_split`.

**Phase 3 — Evaluation harness + golden set + CI gates.** Ragas testset generation + curation; metrics module; LLM-as-judge; eval runs + Evaluations page; `baseline.json`; wire `evals.yml` gates. *Done when:* a PR that worsens retrieval fails CI automatically.

**Phase 4 — Trust layer.** Structured claim output, MiniCheck verification, confidence score, calibrated abstention + calibration job, unanswerable handling; per-claim highlight UI + confidence badge + Settings slider. *Done when:* unsupported_claim_rate ≤ 0.05 and abstention recall ≥ 0.80 on the unanswerable subset.

**Phase 5 — Observability + experiments.** Full span tree persistence, Trace viewer, Analytics dashboard, A/B experiment comparison with bootstrap CIs, online-monitor job. *Done when:* two configs can be compared with significance and every query has a full waterfall.

**Phase 6 — Learning flywheel.** Feedback capture, hard-negative mining, synthetic pairs, embedder + reranker fine-tune jobs, model registry, A/B promotion gate, failure clustering + knowledge-gap analytics; Learning page. *Done when:* a fine-tuned reranker can be trained from feedback and only promotes if its ΔNDCG CI excludes 0.

**Phase 7 — Security layer.** Sanitizer + quarantine, spotlighting, output guard, red-team payload corpus + runner + ASR report; Security page; wire ASR gate into evals nightly. *Done when:* defenses-on ASR ≤ 0.10 and a build fails if ASR regresses.

**Phase 8 — Deploy, harden, document.** Cloud Run + Cloud SQL + GCS + Secret Manager via deploy.yml; k6 load test; README benchmark table + architecture diagram; short "how each metric was measured" writeup. *Done when:* the public Cloud Run demo answers with citations + confidence and the README reports real deltas vs `baseline-v0`.

**Must-have core:** Phases 0–5 + 8. **Differentiators (do in order, don't skip for polish):** 4 (trust), 6 (learning), 7 (security). **Stretch (only if core solid):** ColBERT late-interaction reranker provider, ColPali visual retrieval, HippoRAG2/LazyGraphRAG multi-hop mode, CRAG self-correction loop, judge-jury ensemble.

## 11. Definition of done (whole project)
- `docker compose up` runs the full stack locally; public Cloud Run demo live.
- All must-have phases pass their acceptance criteria; CI + eval gates green on main.
- README has: architecture diagram, feature list, a benchmark table showing metric deltas from `baseline-v0` → final (retrieval, faithfulness, unsupported-claim-rate, abstention precision/coverage, red-team ASR, latency/cost), and a "how measured" note distinguishing self-measured numbers from cited literature.
- Trust, Learning, and Security pages are demoable end-to-end.
- Commit history is meaningful and incremental (verifiability).

## 12. Resume-facing metrics to capture during the build
Record real measured values for: NDCG@10 and hit-rate baseline→final; faithfulness %; unsupported-claim-rate reduction; answered-precision at chosen coverage; reranker fine-tune ΔMRR@10 (with CI); red-team ASR before/after defenses; p95 latency (cached/uncached), first-token latency, cost/query and cache-driven cost reduction; corpus size (docs/chunks) and QPS under k6.
