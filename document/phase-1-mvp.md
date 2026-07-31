# Phase 1 — MVP Vertical Slice

**Status:** complete
**Date:** 2026-07-31
**Spec reference:** `SPEC.md` §10 Phase 1
**Acceptance criteria:** an end-to-end cited answer works and this exact config is saved as experiment `baseline-v0`.

## Goal

Ingest arXiv PDFs → dense retrieve → grounded generation with citations, entirely self-hosted (Docling/pypdf → `bge-small-en-v1.5` embeddings → pgvector → Ollama), with a minimal Playground chat UI, OpenInference spans from day one, and a deterministic mini eval giving `baseline-v0` its first real numbers.

## What was built

- **Ingestion pipeline** (`app/ingestion/`): Docling primary parser with a pypdf fallback, a recursive paragraph/sentence chunker that uses the embedding model's *own* tokenizer for token counting (so chunks reliably fit its context window), sha256 content hashing, all wired as a Celery task behind `POST /api/ingest` + `GET/DELETE /api/documents`.
- **Providers** (`app/providers/`): `BgeSmallEmbeddingProvider` (with BGE's documented asymmetric query-instruction prefix), `OllamaProvider` speaking Ollama's `/api/chat`, and a `BudgetGuard` (Redis-backed daily call/token caps) — inert in Phase 1 since Ollama has no per-call cost, but exercised and ready for Phase 2/3's free-tier Gemini use.
- **Retrieval** (`app/retrieval/`): pgvector HNSW cosine search (`dense.py`) plus a greedy rank-order context assembler (`assembly.py`) that respects `MAX_CONTEXT_TOKENS`, exposed via a debug `POST /api/retrieve` endpoint (dense score only — sparse/RRF/rerank land in Phase 2).
- **Generation** (`app/generation/`): grounded system prompt with basic prompt-level spotlighting, plain-prose generation with inline `[chunk_id=...]` citation markers parsed back into structured `{text, citations}` claims — see "What changed from the original design" below for why this isn't JSON-schema-constrained output.
- **Data model**: `documents`, `chunks` (plain float32 `vector(384)`, HNSW index m=16/ef_construction=200), `queries`, `answers` — the Phase 1 subset of SPEC.md §5, with later phases' columns (parent_id, context_prefix, tsv, claims/confidence, etc.) deferred to when those features actually land.
- **Observability**: manual OpenInference span-kind tagging (`CHAIN`/`RETRIEVER`/`EMBEDDING`/`LLM`) around the `/query` pipeline via the OTel SDK — full span persistence + trace viewer is Phase 5.
- **Frontend**: a minimal Playground chat page (question box → answer with inline citation markers, confidence/insufficient-context state, model + latency footer).
- **Scripts**: `scripts/seed_demo_corpus.py` (discovers real arXiv papers via arXiv's search API — deliberately not a hardcoded id list, see DECISIONS.md — downloads and ingests them) and `scripts/run_eval.py` (deterministic hit_rate@k/MRR/NDCG@10 against a hand-curated mini golden set, no LLM judge).
- **Demo corpus**: 40 arXiv LLM/RAG papers, 707 pages, 1492 chunks, **100% parsed via Docling** (0 pypdf fallbacks — the libxcb fix below held for the whole corpus).
- **Tests**: 19 backend unit tests (up from 2 in Phase 0) covering hashing, chunking, context assembly, and citation parsing — all genuinely exercising deterministic logic, no mocked LLM needed.

## What changed from the original design (and why)

Full rationale and exact fixes are in `DECISIONS.md`; summary of what surfaced only once this was actually run against real hardware and a real model:

1. **JSON-schema-constrained generation → plain prose + parsed citations.** Under Ollama's grammar-constrained decoding, the 4B local model reliably took the shortcut the schema didn't forbid (empty answer + `insufficient_context: true`) on questions the context clearly answered. The identical prompt/context with unconstrained generation answered correctly, cited correctly, and ran ~6x faster. This turned out to collapse two previously-separate designs (structured `/query`, prose-parsed `/query/stream`) into one.
2. **A citation-parsing bug unit tests caught that manual testing hadn't**: a naive sentence splitter orphaned citations placed after a sentence's punctuation-plus-space into their own dropped fragment. Fixed with a capture-group-based splitter; see DECISIONS.md for the regex-backtracking subtlety that made the first attempted fix still fail.
3. **Citation-ID hygiene**: local models can fabricate a plausible-looking `chunk_id` instead of copying a real one. Citations are now filtered against the actual chunk ids sent to the model — cheap, deterministic, and distinct from Phase 4's real claim-verification (which checks whether the *content* is actually supported, not just whether the id is real).
4. **Ollama's context window and generation timeout**: Ollama silently caps at 4096 tokens regardless of model capability (a 400 error, not a truncation) — added `OLLAMA_NUM_CTX=8192`. CPU inference of a ~6000-token context is genuinely slow and variable (observed range: 64s–406s for a single query depending on context size and system load) — `GEN_TIMEOUT_SECONDS=600`. Neither is a bug; both are the documented 8GB-CPU-profile tradeoff (implementation-plan.md §2.E) made concrete.
5. **Backend Docker build**: CPU-only torch/torchvision wheels (PyPI's default CUDA-bundled torch repeatedly stalled downloading through Docker Desktop's network layer on this machine) and `libxcb1`+friends for Docling's table-structure model (without them, ingestion silently degrades to pypdf).
6. **A Celery/asyncio bug**: per-task `asyncio.run()` event loops vs. a shared module-level async engine pool caused intermittent `RuntimeError: attached to a different loop` failures during seeding — fixed by disposing the engine pool at the end of each task.
7. **Docker Desktop instability mid-build**, traced to the C: drive running low on disk space (94% full) after several image rebuilds — relocated Docker's entire WSL2 data disk (~44GB) to the D: drive via an NTFS junction, transparent to Docker Desktop, freeing C: back to 63GB available.

None of these are scope changes to what Phase 1 delivers — all were bugs/environment issues found and fixed while actually proving the vertical slice works, which is the point of building it end-to-end rather than stopping at "the code looks right."

## Verification (measured, this session)

```
Corpus: 40 documents, 1492 chunks, 707 pages — 100% via Docling (0 pypdf fallbacks)

$ python scripts/run_eval.py
Loaded 22 golden-set items (20 answerable)
{
  "hit_rate@10": 1.0,
  "mrr": 0.935,
  "ndcg@10": 0.9509,
  "n_questions": 20
}
→ saved as baselines/baseline.json, experiment "baseline-v0"

$ curl -X POST /api/query -d '{"question": "What is self-attention and how is it used in the Transformer?"}'
→ 5 correctly-cited claims, insufficient_context: false, real chunk_id citations
  verified against the DB (one fabricated citation caught and filtered by
  the citation-hygiene check before this made it to a real query response)

Retrieval sanity check (chain-of-thought question against the full 40-paper corpus):
  top 5 results (by cosine score) — 3 from "Chain-of-Thought Prompting Elicits
  Reasoning" (0.926/0.908/0.900), 2 from "Contrastive Chain-of-Thought
  Prompting" (0.893/0.886) — exactly the two most relevant papers in-corpus.

Generation latency observed (non-streaming, CPU, full pipeline): 64s–406s
depending on context size — smaller context (2500 vs 6000 tokens) cut
latency from ~235-330s to ~74s in a direct comparison on the same question.

$ docker compose down && docker compose up -d
→ all 5 containers healthy; 40 documents / 1492 chunks / migration 0002
  survived the full cycle intact.

$ ruff check . / ruff format --check . / mypy app / pytest tests/unit -v
→ all clean; 19/19 tests passed.

Frontend: rebuilt, HTTP-verified (renders, CORS preflight permits the
frontend origin, JS chunks load 200) — no browser automation tool available
this session, so click-through interaction was not visually verified.
```

## Key decisions this phase

- **Embedding storage stays plain `vector` (not `halfvec`)** for baseline-v0 on purpose — the Phase 2 migration to `halfvec` is then a measured before/after, not an unmeasured starting point (implementation-plan.md §2.E).
- **Docker Compose bind-mounts backend source** (`./backend:/app`) with `uvicorn --reload`, so iterating on Phase 1+ code doesn't require an image rebuild each time — only dependency changes do.
- **Celery worker runs `--pool=solo`**, a deliberate single-process choice to avoid loading a second copy of the embedding model into memory on the 8GB-RAM machine.
- **Chunking token-counts use the embedder's own tokenizer** (not a generic BPE proxy like tiktoken) so chunks reliably fit `bge-small`'s context window — the model is already loaded for embeddings, so this adds no extra dependency.
- **BGE asymmetric retrieval**: queries get the model's documented instruction prefix ("Represent this sentence for searching relevant passages: "); passages don't.
- **Demo corpus discovered via the arXiv API at seed time**, not a hardcoded id list — avoids the risk of a hand-typed, misremembered arXiv id silently corrupting the corpus.
- **Basic prompt-level spotlighting** (`<retrieved_data>` delimiters + "data, not instructions" framing) added now since it's essentially free — not yet validated against attacks; that's Phase 7's red-team suite.
- **Manual OpenInference span-kind tagging** (`openinference.span.kind` attribute) instead of an auto-instrumentation SDK, since we're not using a framework (LlamaIndex/LangChain) those SDKs are built around.
- **Plain prose + parsed citations over JSON-schema-constrained generation** — see "What changed" above; this is the single biggest generation-layer decision this phase.

## What's next

**Phase 2 — Full retrieval engine**: sparse FTS + RRF fusion + cross-encoder reranking + parent-child chunking + contextual enrichment + query rewrite + semantic cache + lost-in-the-middle reorder + incremental re-ingest, plus the filtering architecture (`hnsw.iterative_scan`, partial indexes) and the `vector` → `halfvec` migration, both measured against this phase's `baseline-v0`.
