# ragforge — Implementation Plan

**Status:** DRAFT v2 — awaiting review/approval
**Date:** 2026-07-19 (amended 2026-07-30 — latency architecture, see §2.E)
**Source spec:** `Details-antigravity.txt` (will become `SPEC.md` at repo root in Phase 0)
**This file:** committed as part of the Phase 0 documentation in `document/`

**Amendment log**
- 2026-07-30: added §2.E (latency & scale-benchmarking architecture) and §3.1 (pgvector/query-layer config), following dedicated research into pgvector filtering behavior and RAG latency levers. Full citations in `document/research-latency-optimization.md`. Phase 2 and Phase 8 scope/exit-criteria updated accordingly.

---

## 0. Context and goal

This is a portfolio project whose real deliverable is **resume impact**: a public GitHub repo with a verifiable, incremental build history, measured benchmark numbers, and quantified resume bullets rich in the keywords ATS systems and recruiters scan for (RAG, hybrid retrieval, vector database, LLM evaluation, observability, prompt-injection defense, fine-tuning, CI/CD, Docker, GCP).

End-state artifacts that serve that goal:

1. Public repo `ragforge` with phase-tagged history on `main`.
2. Live $0/month cloud demo (Cloud Run + free-tier Postgres/Redis).
3. README with architecture diagram, GIF demo, and a benchmark table of **measured deltas** (baseline-v0 → final).
4. `document/` — one recruiter-readable report per phase (problem → design → measured result → screenshot).
5. `document/resume-bullets.md` — quantified, ATS-keyword-rich bullets accumulated per phase while numbers are fresh.

## 1. Locked decisions from kickoff Q&A (2026-07-19)

| Decision | Choice | Consequence |
|---|---|---|
| LLM strategy | **Self-hosted first** (user: APIs too expensive) | Local models via an OpenAI-compatible provider (Ollama default). Spec's Gemini-only stack is replaced by a swappable provider layer; see §3. |
| Cloud demo budget | **~$0 free-tier stack** | Cloud Run scale-to-zero (API/frontend) + Neon or Supabase free Postgres w/ pgvector + Upstash free Redis. No Cloud SQL, no Memorystore. |
| Demo corpus | **arXiv LLM/RAG papers** (30–50) | Recognizable to interviewers; stresses Docling (two-column, tables, math); freely redistributable via a seed script. |
| Local hardware | **8GB RAM, CPU only (Windows 11 Home)** | Slim model profile (§3), WSL2 memory cap, lazy model loading, honest latency targets. Fine-tuning targets small models (feasible on CPU/Colab). |

> **Open recommendation (needs your call, §6 Q1):** keep the system 100% self-hosted by default, but allow an *optional free* Google AI Studio key (no credit card, $0) for exactly three offline jobs where a 4B local model is weakest: golden-testset generation, LLM-as-judge scoring, and contextual enrichment. A hard budget guard in code would cap usage inside the free tier so it can never bill. Pure self-hosted works too — the plan marks what degrades.

## 2. Amendments to SPEC.md

Grouped; each will be recorded in `DECISIONS.md` when applied.

### A. Corrections to the spec

- **A1 — Phase-2 exit gate is circular.** Spec Phase 2 requires "NDCG@10 beats baseline-v0 on ci_split", but the golden set + eval harness only exist in Phase 3. Fix: Phase 1 ships a mini golden set (`eval-datasets/v0/mini.jsonl`, ~20 hand-curated items) + `scripts/run_eval.py` computing deterministic retrieval metrics (hit_rate@k, MRR, NDCG@10) with no LLM judge. Baseline-v0 gets real numbers on day one; Phase 2 has a measurable gate; Phase 3 formalizes.
- **A2 — Streaming vs structured output conflict (spec §3.3).** One call can't both stream prose and return strict JSON. Resolution: `POST /query` = non-streaming structured JSON; `POST /query/stream` = stream text with inline citation markers `[c12]`, parse sentences+citations at end-of-stream, run claim verification, emit trust payload as terminal SSE event.
- **A3 — sentence-transformers version.** `CrossEncoderTrainer` requires v4+; spec says v3. Pin latest (≥4.x).
- **A4 — pgvector bootstrap.** First Alembic migration must run `CREATE EXTENSION IF NOT EXISTS vector`; compose uses the `pgvector/pgvector:pg16` image. Embedding column becomes `vector(EMBEDDING_DIM)` driven by env (default **384**, see §3) instead of hard-coded 768; switching dim/provider triggers a re-embed job.
- **A5 — Model currency.** All model names stay env-driven; at each phase start we verify current best small checkpoints rather than hard-committing to 2025-era names.

### B. Self-hosted / 8GB adaptations (replaces spec's locked Gemini choices)

- **B1 — Provider layer.** `LLMProvider` speaks the OpenAI-compatible chat-completions API → works with Ollama (default), LM Studio, llama.cpp server, vLLM, or any hosted endpoint later. A `GeminiProvider` remains available but optional. Same pattern for `EmbeddingProvider` (sentence-transformers default) and `RerankerProvider`.
- **B2 — Slim model lineup** (§3): 4B-class quantized generator, 33M embedder, 23M reranker, RoBERTa-size NLI. Total resident footprint ≤ ~4.5GB with lazy loading.
- **B3 — Ollama runs natively on the Windows host** (not inside Docker/WSL) so model RAM lives outside the WSL2 cap; containers reach it via `host.docker.internal:11434`. `.wslconfig` caps WSL2 at ~4GB.
- **B4 — Honest latency targets per profile.** Spec's p95 ≤ 3.0s applies to the API-provider profile only. Local CPU profile: report measured first-token and full-answer latency (streaming makes 15–40s answers usable); k6 load tests target `/retrieve` and the cached path, not CPU generation. The README will report both profiles — the tradeoff itself is a good engineering story.
- **B5 — Golden set resized** to ~120 items (55 single-hop, 30 multi-hop, 25 unanswerable, 10 adversarial); splits 120 full / 40 calibration / 30 CI. Keeps judge runtime and any free-tier quota feasible; still statistically meaningful for the gates.
- **B6 — Quality targets recalibrated after Phase 1.** Retrieval targets (hit_rate, NDCG) stand as spec'd. Generation-quality targets (faithfulness ≥0.85, answer_correctness ≥0.75) were set assuming Gemini-class generation; with a 4B local model we measure the Phase-1 baseline first, then fix targets in `baselines/baseline.json`.
- **B7 — Fine-tuning (Phase 6) becomes *more* feasible:** bge-small (33M) embedder and MiniLM reranker fine-tune on CPU overnight or free Colab in minutes — and "fine-tuned a 33M embedder on mined user feedback, +X NDCG@10 (95% CI)" is a stronger, fully-reproducible resume bullet.

### C. Cost & reliability guardrails

- **C1 — Budget guard.** Global daily call/token caps per provider (`MAX_DAILY_LLM_CALLS`, token budget) + cost counters already in spans; hard-stop + clear error when exceeded. Backoff/retry for any rate-limited provider.
- **C2 — Judge-score caching** keyed by `(question_id, answer_hash, judge_model, prompt_version)` — eval reruns only pay/compute for changed answers.
- **C3 — CI gate flakiness.** Hard-fail gates only on deterministic retrieval metrics; LLM-judge metrics gate as soft-fail/warn (or 2-run median) — otherwise PRs fail randomly on judge noise. Amends spec §7.2 semantics.
- **C4 — Public-demo hardening (Phase 8):** per-IP rate limit, uploads disabled or tightly capped for anonymous visitors, global daily kill-switch.
- **C5 — Enrichment cost control:** contextual enrichment batched, capped per document, feature-flagged per corpus (it's 1 LLM call per chunk — the most expensive ingest step).

### D. Resume-impact upgrades

- **D1 — `document/` phase reports** written recruiter-readable: problem → design → measured result (+ screenshot). Double as interview prep and blog material.
- **D2 — `document/resume-bullets.md`** updated at each phase close with measured numbers and ATS keywords.
- **D3 — Git tags** `phase-0` … `phase-8` + conventional commits → verifiable incremental history (spec §11).
- **D4 — Publish fine-tuned models to Hugging Face Hub** under your account (free hosting, extra portfolio surface) instead of committing weights to git.
- **D5 — README checklist:** badges, mermaid architecture diagram, GIF demo, benchmark delta table, live-demo link, "how each metric was measured" note distinguishing self-measured vs literature numbers.
- **D6 — Repo hygiene:** MIT LICENSE, `.gitignore`, `.env.example`, no model/blob artifacts in git (JSONL datasets are fine).

### E. Latency & scale-benchmarking architecture (added 2026-07-30)

Triggered by a claim that metadata pre-filtering beats post-filtering for vector search (12ms/wrong-category vs 45ms/87% recall vs 18ms/95% recall on 1M docs). Research (full detail + citations in `document/research-latency-optimization.md`) found the *specific numbers unsourced*, but the *underlying architecture problem real and independently documented* — pgvector's own README describes exactly this failure mode. That gives us a stronger, reproducible story than repeating someone else's numbers: reproduce pgvector's own documented problem, then measure our own fix.

- **E1 — Filtering architecture (replaces naive default filtering).** pgvector has no cost-based pre/post-filter planner (unlike Pinecone/Weaviate/Qdrant) — filtering strategy must be architected explicitly:
  - Set `hnsw.iterative_scan = relaxed_order` as the default for all filtered queries (pgvector ≥0.8.0; neutralizes the documented "selective filter silently returns fewer than k rows" bug). One GUC, highest ROI.
  - Partial HNSW indexes for known low-cardinality metadata filters (e.g. `document_id`/`corpus_version`).
  - Generous `hnsw.max_scan_tuples` + query timeout guard for higher-cardinality/ad-hoc filters relying on iterative scan.
  - Pin **pgvector ≥ 0.8.2** unconditionally (buffer-overflow CVE in parallel HNSW builds, fixed 0.8.2).
- **E2 — Query-layer latency levers**, roughly ranked by impact/effort (full table in research doc): (1) `ef_search` tuning — live-tunable, no rebuild, biggest single lever; (2) iterative scan (E1); (3) `halfvec` (fp16) quantization — ~2x memory cut, <1% recall loss; (4) pgbouncer connection pooling — helps materially only past a concurrency threshold, must demonstrate the crossover point rather than claim pooling is unconditionally faster; (5) asyncpg over sync driver; (6) semantic cache — **report our own measured hit rate**, not the marketed 90–95% (that figure conflates match-accuracy with hit-frequency; real production rates run 20–45%); (7) reranker early-exit / cascade on score margin — real SIGIR-2025-documented technique, but a proxy heuristic that can silently hurt exactly the ambiguous queries reranking is meant to help, so measure and disclose the risk rather than presenting it as free latency; (8) reranker model-size choice (MiniLM vs bge-reranker-v2-m3 vs ColBERT) — measure on our own hardware, published numbers vary 2–3x by source.
- **E3 — Large-scale synthetic benchmark (separate from the real demo corpus), capped at $0 (§6 Q7 resolved).** The real arXiv demo corpus is small (a few thousand chunks) — not enough to say anything credible about behavior at scale. Build a *second*, clearly-labeled benchmark index using a real public embedding dataset dimension-matched to our default embedder (**`abokbot/wikipedia-embedding`, 384-dim** — matches `bge-small-en-v1.5`), sized at **~250K–500K vectors** (the slice that's actually buildable on the local 8GB machine, per E7 — no cloud spend), with our own real arXiv chunks unioned in as tagged "needle" vectors so we can report recall@k for retrieving our own data out of the haystack. This mirrors the BigVectorBench (VLDB 2025) methodology for exactly this construction — our strongest methodological citation against a "vanity benchmark" critique. Never use `np.random.randn()` synthetic vectors — random-Gaussian nearest-neighbor structure doesn't resemble real embedding geometry and is an immediate tell to anyone who's done ANN benchmarking.
- **E4 — Multi-architecture sweep, not a single predetermined config.** Don't just implement one "best practice" from the research and call it done — empirically sweep the candidate architectures on our own data/hardware and let the numbers pick the winner, since the research (§2.E1, `research-latency-optimization.md`) shows no single approach wins at every selectivity. On both the real corpus (Phase 2) and the capped synthetic benchmark (Phase 8), run the full cross-product and report all of it, not just the winner:
  - **Filtering strategy:** naive post-filter (pgvector default) × partial-index pre-filter × `hnsw.iterative_scan=relaxed_order` × `strict_order`, each at several filter selectivities (e.g. ~5%, ~20%, ~50%, ~80% of rows matching).
  - **Index/storage:** `vector` (float32) × `halfvec` (fp16) — latency, memory, and recall@k for each.
  - **HNSW tuning:** a small `ef_search` sweep (e.g. 40/80/160/320) crossed with the above, to get the recall/latency curve rather than one point on it.
  - **Concurrency:** each surviving config re-measured under k6-driven concurrent load (not just single-query), plus the pgbouncer-vs-direct-connection crossover point (E2.4).
  - Report the winning configuration per selectivity band plus the full table — "here's what we tried, here's what actually won, here's why" is a stronger resume/interview artifact than a single number, and it's the honest answer to "why did you pick this architecture."
- **E5 — Benchmark rigor.** Report cold vs warm latency separately; p50/p95/p99 (never just mean); ≥30–50 executions per configuration after warmup, repeated across full trials to show run-to-run variance controlled; recall@k against brute-force ground truth on the same vector set.
- **E6 — Tooling.** Hand-rolled brute-force-groundtruth script (simpler to wire into our own schema/filters than adapting an existing adapter) for the recall@k / `ef_search` / filtering-strategy sweep (E4); **k6** for end-to-end FastAPI latency + concurrency/pooling story; `pgbench` as a lower-layer sanity check.
- **E7 — 8GB-machine build constraint (drives the $0 cap in E3).** Memory math + pgvector's own build-time reports say a full 1M-vector HNSW index (~10–25GB with graph overhead) is not buildable locally on this machine — the realistic spare `maintenance_work_mem` after Windows/Docker Desktop overhead is ~2–3GB, which forces the slow disk-based build path. Decision: cap the synthetic benchmark at ~250K–500K vectors (384-dim, `halfvec`-quantized), which fits comfortably — no cloud VM, genuinely $0, still far larger than the real demo corpus. Regardless of scale: explicit `shm_size` ≥ `maintenance_work_mem` in compose (Docker's 64MB default silently crashes parallel HNSW builds hours in — pgvector issue #959), `max_parallel_maintenance_workers` kept conservative (2–3), pgvector pinned ≥0.8.2.

## 3. Model lineup (8GB CPU profile, all env-swappable)

| Role | Default (slim) | Size | Upgrade path |
|---|---|---|---|
| Generation | Qwen3-4B-Instruct (Q4, via Ollama) | ~2.5GB, loaded on demand | any OpenAI-compatible endpoint or Gemini |
| Embeddings | `BAAI/bge-small-en-v1.5` (384-dim) | ~130MB | bge-base/bge-m3/gemini-embedding |
| Reranker | `cross-encoder/ms-marco-MiniLM-L-6-v2` | ~90MB | bge-reranker-base / v2-m3 / Cohere API |
| Claim verification | MiniCheck RoBERTa-Large | ~1.4GB, lazy-load in worker | MiniCheck Flan-T5-Large |
| LLM-as-judge | free Gemini key (recommended) **or** local generator | — | see §6 Q1 |
| Fine-tune targets | bge-small embedder + MiniLM reranker | tiny | CPU/Colab feasible |

### 3.1 pgvector & query-layer configuration (latency architecture, §2.E)

| Setting | Default | Purpose |
|---|---|---|
| pgvector version | ≥ 0.8.2 (pinned) | buffer-overflow CVE fixed in 0.8.2; iterative scan requires ≥0.8.0 |
| `hnsw.iterative_scan` | `relaxed_order` | neutralizes documented post-filter under-return bug |
| `hnsw.max_scan_tuples` | 20,000–60,000 (tune per corpus) | bound on iterative-scan traversal depth |
| `hnsw.ef_search` | 80 default; tuned per experiment (E2) | primary recall/latency tradeoff knob, no rebuild needed |
| Embedding storage | `halfvec` (fp16) | ~2x memory cut, <1% measured recall loss on normalized embeddings |
| Partial HNSW indexes | per low-cardinality metadata filter | true pre-filter path for known filter values |
| DB driver | asyncpg | async I/O under concurrent load |
| Connection pooling | pgbouncer (measure crossover point, don't assume it always wins) | throughput/latency under concurrent load only |
| Docker `shm_size` | ≥ `maintenance_work_mem` | prevents silent parallel-HNSW-build crash (default 64MB is a trap) |

## 4. Phase plan (build order, each phase gated by acceptance criteria)

| Phase | Scope (spec §10 + amendments) | Exit criteria | Doc | Est. sessions |
|---|---|---|---|---|
| **0 — Scaffold** | git init on `main`; spec → `SPEC.md`; `DECISIONS.md`; monorepo skeleton; docker-compose (api, frontend, postgres/pgvector, redis, worker); `config.py`; health/ready; Alembic init (A4); CI lint+unit skeleton; LICENSE/.gitignore/.env.example; `.wslconfig` guidance (B3) | `docker compose up` serves empty API + blank frontend; CI green; **first push (you provide repo URL)** | `phase-0-scaffold.md` | 1–2 |
| **1 — MVP vertical slice** | Ingest arXiv PDFs (Docling → chunks → bge-small embeddings → pgvector) → dense retrieve → grounded generation with citations via Ollama → minimal Playground; OpenInference spans from day one; seed script (30–50 arXiv papers); mini golden set + `run_eval.py` (A1); budget guard (C1) | End-to-end cited answer works; config saved as experiment `baseline-v0` with measured retrieval numbers | `phase-1-mvp.md` | 2–3 |
| **2 — Full retrieval engine** | Sparse FTS + RRF + MiniLM reranker + parent-child chunks + contextual enrichment (C5, flagged) + query rewrite + semantic cache + lost-in-the-middle reorder + incremental re-ingest; **filtering architecture (E1): iterative scan + partial indexes, replacing pgvector's naive post-filter default**; `ef_search` tuning curve measured on real corpus (E2.1); Retrieval Inspector page | `/retrieve` shows all 4 score types; NDCG@10 beats baseline-v0 on mini set; **recall@k / latency curve reproduces then fixes pgvector's documented filtered-search failure mode, measured on the real corpus** | `phase-2-retrieval.md` | 2–3 |
| **3 — Eval harness + CI gates** | Golden set v1 (~120 items, B5) + curation; Ragas metrics + custom judge (C2); eval runs + Evaluations page; `baselines/baseline.json` (B6); `evals.yml` gates (C3) | A PR that worsens retrieval fails CI automatically | `phase-3-evals.md` | 2–3 |
| **4 — Trust layer** | Structured claims (A2); MiniCheck verification; confidence score; calibrated abstention + calibration job; per-claim highlight UI + confidence badge + Settings slider | unsupported_claim_rate & abstention recall targets met on unanswerable subset (thresholds per B6 baseline) | `phase-4-trust.md` | 2 |
| **5 — Observability + experiments** | Span persistence + Trace viewer waterfall; Analytics dashboard; A/B experiment comparison with bootstrap CIs; online-monitor job | Two configs comparable with CIs; every query has a full waterfall | `phase-5-observability.md` | 2–3 |
| **6 — Learning flywheel** | Feedback capture; hard-negative mining; synthetic pairs; fine-tune bge-small + MiniLM (B7); model registry; A/B promotion gate; failure clustering; Learning page; publish to HF Hub (D4) | Fine-tuned reranker trains from feedback; promotes only if ΔNDCG CI excludes 0 | `phase-6-learning.md` | 3 |
| **7 — Security layer** | Sanitizer + quarantine; spotlighting; output guard; red-team corpus (≥60 payloads) + runner + ASR report; Security page; ASR gate in nightly | Defenses-on ASR ≤ 0.10; build fails if ASR regresses | `phase-7-security.md` | 2 |
| **8 — Deploy + document** | Cloud Run (api/frontend, scale-to-zero) + Neon/Supabase pgvector + Upstash Redis + GCS + Secret Manager via `deploy.yml`; demo LLM = free Gemini key (§6 Q2 resolved); demo hardening (C4); **large-scale synthetic benchmark (E3), built locally, $0 (§6 Q7 resolved): ~250K–500K vector index (`abokbot/wikipedia-embedding`, 384-dim, our real chunks unioned in as needles), full multi-architecture sweep — filtering strategy × float32/halfvec × ef_search × concurrency (E4), k6 + pgbouncer crossover test**; README polish (D5); final benchmark table + resume bullets (D2) | Public demo live answering with citations + confidence; README reports real deltas vs baseline-v0; **benchmark report with p50/p95/p99, recall@k, and the full architecture-sweep table (not just the winning config) at ~250K–500K vector scale, clearly labeled as a separate synthetic benchmark from the live demo corpus** | `phase-8-deploy.md` | 3–4 |

**Total estimate:** ~19–23 working sessions (Phase 8 grew by ~1 session for the large-scale latency benchmark, §2.E). Must-have core = Phases 0–5 + 8; differentiators in order 4 → 6 → 7 (per spec §10). Stretch items (ColBERT, ColPali, GraphRAG, CRAG) only after everything above is solid.

## 5. Git & documentation workflow (your requirements, operationalized)

- Single branch `main`; small conventional commits (`feat:`, `fix:`, `test:`, `chore:`, `docs:`) during a phase; **push at phase completion**; git tag `phase-N` on the phase-closing commit.
- `document/` folder at repo root. Each phase closes with: acceptance-criteria check → write `document/phase-N-*.md` → update `document/resume-bullets.md` → commit docs → tag → push.
- **First commit/push happens at Phase 0 close — you provide the GitHub repository URL then.** Repo should be **public** (required for resume verifiability + free GitHub Actions).
- `DECISIONS.md` records every deviation from SPEC.md with a one-line rationale.

## 6. Open questions

**Resolved (2026-07-30):**
1. ~~Pure self-hosted vs hybrid~~ → **Hybrid**: free Google AI Studio key for testset generation, LLM-as-judge, and enrichment; local Ollama model does all in-app generation; hard budget guard keeps the key inside the free tier.
2. ~~Public demo generation LLM~~ → **Free Gemini key powers the live demo** (snappy, capped to stay free).
3. ~~Repo name & visibility~~ → **`ragforge`, public.**
4. ~~Repo root~~ → **`d:\RAG_PROJECT` is the repo root.**
6. ~~Ollama~~ → **Install natively on Windows** (outside Docker, reached via `host.docker.internal:11434`).

7. ~~One-time cloud spend for the large-scale latency benchmark~~ → **$0 — no cloud VM.** Cap the synthetic benchmark at ~250K–500K vectors (384-dim, `halfvec`-quantized), buildable locally on the 8GB machine. §2.E3/E7 updated accordingly, plus a multi-architecture sweep (§2.E4) so the "best latency" claim is empirically derived on our own hardware, not assumed from any single source.

**Still open:**
5. **Timeline:** any deadline (e.g., applications starting month X)? Determines whether we trim toward the must-have core. No deadline given yet — proceeding at a steady phase-by-phase pace; flag if a deadline emerges so we can trim toward the must-have core (Phases 0–5 + 8).

## 7. Risks & mitigations

| Risk | Mitigation |
|---|---|
| 8GB RAM pressure (models + Docker + IDE) | Slim lineup (§3), Ollama on host, lazy loading, WSL2 cap, close-what's-unused discipline; worst case swap reranker/NLI to even smaller checkpoints |
| 4B model quality (JSON compliance, faithfulness) | Structured-output retries + schema validation; citation-marker fallback (A2); measure honestly, report as profile tradeoff |
| LLM-judge noise breaks CI | C2 caching + C3 soft gates + deterministic retrieval hard gates |
| Ragas ↔ local-LLM integration friction | Custom judge/metrics fallback already spec'd; Ragas used where it works (testset gen, standard metrics) |
| Free-tier limits (if hybrid) | C1 budget guard, batch + cache everything, nightly not per-commit for expensive evals |
| Public demo abuse | C4 hardening |
| Scope creep (spec is huge) | Phase gates + must-have core first; stretch only at the end |
| Windows-native Python pain (torch/docling) | Everything backend runs in Docker/WSL2; only Ollama runs native |
| 1M-vector HNSW index unbuildable on local 8GB machine (§2.E7) | Capped the synthetic benchmark at ~250K–500K vectors (`halfvec`, 384-dim) instead — fits locally, genuinely $0 (§6 Q7); pin pgvector ≥0.8.2 and set Docker `shm_size` explicitly to avoid the silent parallel-build crash |
| Latency benchmark reads as a "vanity benchmark" | Real, dimension-matched public embedding dataset with our own chunks unioned in as needles (§2.E3), not synthetic random vectors; full multi-architecture sweep reported, not a single cherry-picked winning number (§2.E4); cold/warm + p50/p95/p99 + recall@k against brute-force ground truth (§2.E5) |
| "Best latency" claim turns out to be architecture-dependent, no single config wins everywhere | Expected and planned for (§2.E4) — report the full sweep table (filtering strategy × selectivity × quantization × ef_search × concurrency) and the winning config per band, rather than forcing one number; this is itself the more credible engineering story |

## 8. Definition of done (mirrors spec §11 + resume goal)

- `docker compose up` runs the full stack locally on the 8GB profile; public demo live.
- Must-have phases pass acceptance criteria; CI + eval gates green on `main`.
- README: architecture diagram, feature list, benchmark table (baseline-v0 → final deltas for retrieval, faithfulness, unsupported-claim rate, abstention precision/coverage, red-team ASR, latency/cost), "how measured" note.
- Trust, Learning, Security pages demoable end-to-end.
- `document/` has all phase reports + `resume-bullets.md` with measured, quantified bullets + `research-latency-optimization.md` (source-of-record citations) + a dedicated large-scale latency/filtering benchmark report (§2.E) clearly distinguishing the real demo-corpus numbers from the synthetic at-scale numbers.
