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
