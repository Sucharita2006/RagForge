# Research: RAG retrieval latency optimization (pgvector-based stack)

**Date:** 2026-07-30
**Trigger:** a social-media post claiming pre-filtering vector search beats post-filtering (12ms/wrong-category vs 45ms/87% recall vs 18ms/95% recall on a 1M-doc corpus), with the heuristic "pre-filter <10% selectivity, post-filter >50%, staged hybrid between."
**Purpose:** verify that claim against real pgvector behavior and current literature, and identify defensible, implementable latency optimizations for `ragforge` with numbers a technical interviewer would accept as genuine rather than dismiss as a vanity benchmark.

This file is the source-of-record for citations. `implementation-plan.md` §2.E and the phase table carry only the synthesized decisions.

---

## Verdict on the trigger post

The **direction** of the claim is real and matches both pgvector's own documented behavior and academic literature. The **specific numbers** (12ms/45ms/18ms, 87%/95% recall, the clean 10%/50% cutoffs) are unsourced round numbers typical of LinkedIn-style content — not a citable benchmark. We will not repeat them; we will reproduce our own version of this experiment and report real measured numbers instead.

Two things corroborate the *shape* of the claim:
- pgvector's own README documents that with the default `hnsw.ef_search=40`, a naive post-filter query against a 10%-selective `WHERE` clause returns only ~4 rows on average instead of the requested k — this is pgvector's own literal example, not a vendor exaggeration. Corroborated independently by Supabase and pgEdge docs.
- A SIGMOD 2026 paper (Lu et al., "An In-Depth Study of Filter-Agnostic Vector Search," arXiv:2603.23710) found filter-first methods win at 1–30% selectivity (up to 100x fewer distance computations at 1%), traversal-first/post-filter-style methods become competitive around 10% and superior above 30% — no universal winner across the whole range. Caveat: tests research-index prototypes (NaviX, ACORN, ScaNN), not vanilla pgvector HNSW, so it validates the *shape*, not pgvector's numbers specifically.

What the post gets wrong: it implies pgvector has a cost-based planner that auto-selects pre/post-filter strategy the way Pinecone/Weaviate/Qdrant's integrated filtering does. It does not — you must architect this yourself (partial indexes, partitioning, iterative scan), or accept the default post-filter behavior and its documented failure mode.

## (a) Filtering architecture — recommended decision

**pgvector's actual behavior (v0.8.0+, stable is 0.8.6):**

1. Default HNSW + `WHERE` = **post-filter**: pgvector fetches `ef_search` (default 40) candidates from the graph, *then* Postgres applies the filter. A selective filter silently returns fewer than k rows. (pgvector README; GitHub issue #843; ParadeDB's pgvector-limitations page.)
2. **pgvector 0.8.0 (Nov 2024) added iterative index scans** — `hnsw.iterative_scan` GUC (`off` / `strict_order` / `relaxed_order`, default off). When enabled, pgvector keeps traversing the graph until enough filtered rows are found or `hnsw.max_scan_tuples` (default 20,000) is hit, bounded by `hnsw.scan_mem_multiplier` (default 1x `work_mem`). This is an *adaptive post-filter*, not true pre-filtering, but it closes most of the practical gap at low-to-medium selectivity. (pgvector README; Nile & AWS Aurora pgvector-0.8.0 posts; pgEdge filtering docs.)
3. **True pre-filtering in pgvector is manual**: partial HNSW indexes per known filter value (`CREATE INDEX ... WHERE category_id = 123`), table partitioning by filter column for many distinct values, or a CTE that filters first via a btree index then does exact brute-force distance only on survivors (viable when the filter is very selective — the "search" degenerates into a small sequential scan). (pgvector README; ClickHouse engineering blog — independent, non-pgvector-vendor source recommending the same patterns.)

**Decision for ragforge:**
- Set `hnsw.iterative_scan = relaxed_order` as the default for all filtered queries — one GUC, directly neutralizes the "post-filter returns garbage" failure mode. Highest ROI, lowest effort.
- Add partial HNSW indexes for known low-cardinality metadata filters (e.g. `document_id`/`corpus_version`/`tags` if cardinality stays small).
- For higher-cardinality/ad-hoc filters, rely on iterative scan with a generous `hnsw.max_scan_tuples` and a query timeout guard.
- Honest framing for the README: pgvector has no cost-based automatic pre/post-filter planner like Pinecone/Qdrant/Weaviate — state this directly rather than implying pgvector "just handles it."
- Narrative: "measured pgvector's own documented pre-0.8 failure mode, then measured the improvement from iterative scan + partial indexes" — reproducible on our own hardware, cites pgvector's own docs as the problem statement, stronger than repeating someone else's numbers.

**Flagged as marketing-only, not cited as fact:** Clarvo's "tens of seconds → single-digit ms" blog headline (no methodology disclosed); VectorChord's "up to 3x faster" prefiltering claim (no dataset/scale disclosed).

## (b) Ranked latency optimizations

| # | Lever | Impact | Effort | Key numbers / caveats |
|---|---|---|---|---|
| 1 | HNSW `ef_search` tuning | High | Low | Non-linear: recall 0.8→0.95 costs ~31% more latency; 0.95→0.99 costs 3-5x more (production benchmark + Jonathan Katz's pgvector HNSW benchmarks, SIFT/GIST/dbpedia). Default 40; production commonly 100-400. No rebuild needed — tune live. |
| 2 | Iterative scan for filtered queries | High (correctness) | Low | Fixes the silent under-return bug directly. |
| 3 | Scalar quantization (`halfvec`/fp16) | Med-High | Low-Med | ~2x memory cut, <1% recall degradation reported on normalized embeddings; used in production at scale per HN discussion. |
| 4 | pgbouncer / connection pooling | Med-High (concurrency only) | Low | +30% throughput, latency 5.3s→4.0s at 1000 concurrent clients in one benchmark; p95/p99 200ms→~100ms. **Caveat: at low concurrency (<~56 clients) direct connections beat pooled 2.5x** — must show the crossover point, not just "pooling is faster." |
| 5 | asyncpg vs sync driver | Medium | Low | ~23% higher throughput vs psycopg3 in one benchmark (single-source, directionally consistent with async I/O reducing wait overhead). |
| 6 | Binary quantization | Medium (big at scale, risky at small) | Medium | 32x smaller index at 100M-vector scale, 2-4% recall drop *after re-ranking candidates*; unsafe used alone. Irrelevant at our real corpus size (few thousand chunks) — only matters for the synthetic large-scale benchmark. |
| 7 | Matryoshka (MRL) truncation | Medium | Low (if MRL-trained model) | 512-dim retains 94-98%, 256-dim retains >88% of full performance in MTEB-style evals. **Counterpoint (2026 paper, arXiv:2605.16608): even non-MRL embeddings tolerate moderate truncation reasonably well** — MRL's edge shows mainly at heavy truncation. Not uniquely magic; requires re-normalizing after truncation. |
| 8 | Embedding dimensionality (384 vs 768 vs 1536) | Med-High | Low (model choice) | Supabase benchmark: 384-dim gte-small beat 1536-dim ada-002 on both QPS and MTEB rank, using 4GB vs 7.5GB RAM. Single-vendor source but mechanism (linear scaling with dim) is basic math. Don't use post-hoc PCA — pick via model choice, not truncation, unless MRL-trained. |
| 9 | Semantic caching (Redis) | Medium, **widely oversold** | Low-Med | Real production hit rates are 20-45%, not the marketed 90-95% (that figure is *match accuracy*, not *hit frequency* — a documented conflation). Where it hits, savings are large (3.2s→0.05s reported). **Report our own measured hit rate on our own query distribution — this is a good "we didn't just believe the vendor number" moment.** |
| 10 | Reranker skip/early-exit on score margin | Medium | Medium | Real, peer-reviewed technique (SIGIR 2025 "Efficient Re-ranking with Cross-encoders via Early Exit"; classical "cascade ranking" going back decades; 2026 adaptive/confidence-aware reranking papers, e.g. CAR arXiv:2605.04495). **Risk: the margin heuristic is a proxy — if miscalibrated, silently ships worse rankings on exactly the ambiguous queries where reranking matters most.** Implement, measure, disclose the risk honestly rather than presenting it as free latency. |
| 11 | Reranker model size choice | High (fixed architecture decision) | Low | MiniLM-class (~22M params) roughly 10-15x faster than bge-reranker-v2-m3 (~568M) for meaningfully lower quality. ColBERT late-interaction competitive on latency, different storage cost. **Numbers vary 2-3x across sources — measure on our own hardware rather than citing blog numbers directly.** |
| 12 | RRF fusion cost | Negligible — confirmed | N/A | O(n log n) rank-sort + hashmap merge; multiple independent sources (OpenSearch, Chroma, Azure AI Search docs) confirm cost is negligible vs. search/rerank. Still worth measuring (<1ms) for a complete, credible-looking table. |

## (c) Benchmarking methodology

**Dataset strategy** (the key to not being dismissed as a vanity benchmark): don't fabricate random vectors — nearest-neighbor structure in `np.random.randn()` vectors doesn't resemble real embedding geometry, and anyone who's done ANN benchmarking will spot it immediately. Instead:

- Use a real public large-scale embedding dataset, dimension-matched to our own default embedder (`bge-small-en-v1.5`, 384-dim) so the benchmark is representative of ragforge's own pipeline:
  - **`abokbot/wikipedia-embedding`** (HF) — 6.46M vectors at 384-dim, MiniLM-encoded Wikipedia paragraphs. Dimension-matched to our stack — **primary recommendation**.
  - Alternatives if we want to also demonstrate the dimensionality-tradeoff lever (#8 above): `KShivendu/dbpedia-entities-openai-1M` (1536-dim, OpenAI ada-002, the dataset the original Supabase/Qdrant-style pgvector benchmarks used) or `Cohere/wikipedia-22-12-en-embeddings` (768-dim).
- **Union our own real arXiv chunks in as tagged "needle" vectors** inside the large public "haystack," then report recall@k specifically for retrieving our own needles out of the 1M-vector haystack. This mirrors the methodology of BigVectorBench (VLDB 2025, github.com/BenchCouncil/BigVectorBench), which builds million-scale sets from real embeddings plus controllable synthetic filter labels (6-80% selectivity) for exactly this kind of selectivity experiment — our strongest methodological citation.

**Rigor:**
- Report **cold vs warm** latency separately (first query after container/index load vs steady-state after warmup) — the gap is large and reporting both reads as more credible than one cherry-picked number.
- Report **p50/p95/p99**, never just mean (industry convention per Qdrant's vector-db-benchmark methodology).
- At least 30-50 query executions per configuration after warmup; repeat full trials (not just within-run) to show run-to-run variance was controlled.
- **recall@k against brute-force ground truth** (exact k-NN, no index) on the same vector set — standard across ANN-Benchmarks, BigVectorBench, and the SIGMOD/VLDB papers reviewed. Ground truth for a modest query sample (100-500 queries) against 1M vectors is feasible on a laptop (it's an embarrassingly parallel matmul) even though building the *index* is the expensive part.
- Report **single-query latency and concurrent-load latency/throughput separately** (k6 ramping virtual users) — this is where the pgbouncer crossover point (lever #4) gets demonstrated honestly.

**Tools:**
- **ANN-Benchmarks** (github.com/erikbern/ann-benchmarks) — has a pgvector adapter; "gold standard" per multiple sources; best for recall-vs-QPS curves at varying `ef_search`.
- **k6** — best for benchmarking our actual FastAPI endpoint end-to-end (embed → hybrid search → RRF → rerank → response); documented pattern for exactly this exists, including Postgres-connection-pool-sizing examples.
- **pgbench** — lower-layer sanity check for raw Postgres/pgvector latency without the API layer.
- **Recommended combination**: a hand-rolled brute-force-groundtruth script (simpler to wire into our own schema/filters than adapting ANN-Benchmarks' adapter) for recall@k / ef_search / pre-filter-vs-post-filter-vs-iterative-scan curves; k6 for end-to-end API latency and the concurrency/pooling story.

## (d) Practical constraints on the 8GB Windows/Docker machine

**Memory math** (rule of thumb: N × D × 4 bytes × 2 for graph overhead, corroborated across a pgvector GitHub issue and an independent scaling write-up):
- 1M vectors at 384-dim ≈ 3GB (raw estimate) but **real-world per-vector overhead with graph metadata runs 20-25KB/vector** at typical m≈16-32, i.e. **20-25GB for the index alone** at 1M vectors, independent of raw vector storage (ClickHouse engineering blog).
- Index build time: "can take 6 minutes" for a modest 1M-row build while "using all available RAM in maintenance_work_mem and redlining the CPU" (Crunchy Data) — that's for a light configuration; higher m/ef_construction is much slower.

**Verdict: building a 1M-vector HNSW index locally on this 8GB Windows/Docker machine is not feasible.** The realistic `maintenance_work_mem` we can spare — after Windows, Docker Desktop overhead (commonly 1-2GB itself), Postgres's other settings — is maybe 2-3GB, which for a ~10-25GB index falls onto the slow disk-based build path (10-50x slower, real OOM/crash risk under Docker Desktop's WSL2 memory ceiling).

**Two additional concrete gotchas, regardless of where we build:**
- **Docker `shm_size` trap**: parallel HNSW builds (pgvector ≥0.6.0) use `/dev/shm` for their working area. Docker's default `/dev/shm` is 64MB regardless of host RAM — if not raised to match `maintenance_work_mem`, parallel workers crash with a cryptic OOM-style error *at the end of an hours-long build* (pgvector issue #959; neondatabase/autoscaling issue #800). Must set `shm_size` explicitly in compose.
- **CVE**: pgvector had a buffer-overflow bug in parallel HNSW builds, fixed in 0.8.2 (referenced as CVE-2026-3172 in the 0.8.2 release notes) — pin to ≥0.8.2 unconditionally.

**Recommendation (reduce the problem, not just the hardware):**
1. Validate correctness locally at a smaller scale (250K-500K vectors, 384-dim, `halfvec` quantized) — this fits comfortably and proves the filtering/quantization logic works.
2. For the headline "at meaningful scale" number (500K-1M vectors), use a short-lived cloud VM (e.g. 16-32GB RAM, a few hours) rather than fighting local RAM — this mirrors the conclusion of independent critiques of pgvector-at-scale (alex-jacobs.com "The Case Against pgvector"; corroborating HN thread) and is itself a legitimate engineering-judgment talking point: "recognized production-representative index builds need production-representative hardware, provisioned it ephemerally rather than over-provisioning the dev box."
3. Regardless of where we build: `shm_size` ≥ `maintenance_work_mem`, pin pgvector ≥0.8.2, keep `max_parallel_maintenance_workers` conservative (2-3) given limited cores.

## Summary: marketing-only vs. corroborated

**Do not cite as fact (marketing-only / single-source):** the trigger post's exact 12/45/18ms and 87%/95% numbers; Clarvo's "tens of seconds → single-digit ms" headline; VectorChord's "3x faster" prefiltering claim; semantic-cache "90-95% hit rate" marketing figures; any single reranker-latency number without disclosed hardware.

**Safe to cite as established (independently corroborated):** pgvector's documented post-filter under-return bug and the iterative-scan fix (pgvector README, corroborated by AWS/Nile/Supabase/pgEdge); the non-linear `ef_search` recall/latency curve shape; the general selectivity-based pre/post-filter tradeoff shape (SIGMOD 2026 paper + multiple engineering blogs, though the specific 10%/50% cutoffs are round-number heuristics, not derived thresholds); real semantic-cache hit rates of 20-45%; RRF's negligible cost; the Docker `shm_size` gotcha.
