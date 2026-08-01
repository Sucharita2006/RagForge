"""Filtering architecture benchmark (implementation-plan.md §2.E1, E4).

Reproduces pgvector's own documented failure mode — a selective metadata
filter combined with a naive post-filter HNSW scan silently returns fewer
than the requested top_k rows — then measures whether `hnsw.iterative_scan`
fixes it, sweeping ef_search too so the tradeoff is a curve, not one point.

Runs against the real corpus (not a synthetic benchmark — that's Phase 8's
job at 250-500K vectors per implementation-plan.md §2.E3/E7). Run inside
the container: `docker compose exec api python scripts/benchmark_filtering.py`

At this corpus's actual scale (~1.5K chunks), Postgres's own cost-based
planner sidesteps the bug on its own: a `document_id` filter is selective
enough that a B-tree index scan + exact sort beats the approximate HNSW
index outright, so `hnsw.ef_search`/`hnsw.iterative_scan` never come into
play (confirmed via EXPLAIN — see the "natural plan" section of the
output). To still exercise and fix the documented failure mode on real
data, the second half of this script temporarily drops the competing
`ix_chunks_document_id` index inside a transaction it always rolls back
(never committed, so the index is restored even on a crash) — this is
what a corpus two orders of magnitude larger would force the planner to
do on its own.
"""

import asyncio
import json
import time
from pathlib import Path

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.session import async_session_maker
from app.models.chunks import Chunk
from app.providers.embeddings.bge_small import get_embedding_provider

settings = get_settings()

TOP_K = 10
EF_SEARCH_VALUES = (10, 40, 80, 160)
ITERATIVE_SCAN_VALUES = ("off", "relaxed_order")
N_RUNS = 5
QUERY = "What method does this paper propose and how does it work?"
FILTER_INDEX_NAME = "ix_chunks_document_id"


async def get_sample_document() -> tuple[str, int, int]:
    """Pick a middle-of-the-pack document by child-chunk count (avoids
    outliers skewing the selectivity story)."""
    async with async_session_maker() as db:
        result = await db.execute(
            select(Chunk.document_id, func.count(Chunk.id))
            .where(Chunk.is_parent.is_(False))
            .group_by(Chunk.document_id)
        )
        rows = result.all()
        total_result = await db.execute(
            select(func.count(Chunk.id)).where(Chunk.is_parent.is_(False))
        )
        total_chunks = total_result.scalar_one()

    rows_sorted = sorted(rows, key=lambda r: r[1])
    doc_id, n_chunks = rows_sorted[len(rows_sorted) // 2]
    return str(doc_id), n_chunks, total_chunks


def _filtered_stmt(document_id: str, query_embedding: list[float]):
    distance = Chunk.embedding.cosine_distance(query_embedding)
    return (
        select(Chunk)
        .where(Chunk.is_parent.is_(False), Chunk.document_id == document_id)
        .order_by(distance)
        .limit(TOP_K)
    )


async def explain_plan(db: AsyncSession, document_id: str, query_embedding: list[float]) -> str:
    # literal_binds compilation can't render pgvector's custom vector type,
    # so this bypasses the ORM statement and binds the embedding as a plain
    # cast SQL literal instead (values are our own floats, not user input).
    vector_literal = "[" + ",".join(str(x) for x in query_embedding) + "]"
    result = await db.execute(
        text(
            f"EXPLAIN ANALYZE SELECT id FROM chunks "
            f"WHERE is_parent = false AND document_id = :document_id "
            f"ORDER BY embedding <=> '{vector_literal}'::halfvec({settings.EMBEDDING_DIM}) "
            f"LIMIT {TOP_K}"
        ),
        {"document_id": document_id},
    )
    return "\n".join(row[0] for row in result.all())


async def run_filtered_search(
    db: AsyncSession,
    document_id: str,
    query_embedding: list[float],
    iterative_scan: str,
    ef_search: int,
) -> tuple[int, float]:
    """Returns (rows_returned, latency_ms) for one filtered query."""
    await db.execute(text(f"SET LOCAL hnsw.ef_search = {ef_search}"))
    await db.execute(text(f"SET LOCAL hnsw.iterative_scan = {iterative_scan}"))
    await db.execute(text(f"SET LOCAL hnsw.max_scan_tuples = {settings.HNSW_MAX_SCAN_TUPLES}"))

    start = time.monotonic()
    result = await db.execute(_filtered_stmt(document_id, query_embedding))
    rows = result.scalars().all()
    latency_ms = (time.monotonic() - start) * 1000
    return len(rows), latency_ms


async def sweep(db: AsyncSession, document_id: str, query_embedding: list[float]) -> list[dict]:
    print(f"{'ef_search':>10} {'iterative_scan':>16} {'avg_rows':>10} {'avg_latency_ms':>16}")
    results = []
    for ef_search in EF_SEARCH_VALUES:
        for iterative_scan in ITERATIVE_SCAN_VALUES:
            row_counts, latencies = [], []
            for _ in range(N_RUNS):
                n_rows, latency_ms = await run_filtered_search(
                    db, document_id, query_embedding, iterative_scan, ef_search
                )
                row_counts.append(n_rows)
                latencies.append(latency_ms)
            avg_rows = sum(row_counts) / len(row_counts)
            avg_latency = sum(latencies) / len(latencies)
            print(f"{ef_search:>10} {iterative_scan:>16} {avg_rows:>10.1f} {avg_latency:>16.2f}")
            results.append(
                {
                    "ef_search": ef_search,
                    "iterative_scan": iterative_scan,
                    "avg_rows_returned": avg_rows,
                    "avg_latency_ms": avg_latency,
                }
            )
    return results


async def main() -> None:
    embedder = get_embedding_provider()
    document_id, n_chunks, total_chunks = await get_sample_document()
    selectivity = n_chunks / total_chunks

    print(f"Sample document: {document_id}")
    print(
        f"  chunks in document: {n_chunks} / {total_chunks} total ({selectivity:.1%} selectivity)"
    )
    print(f"Query: {QUERY!r}")
    print(f"Requesting top_k={TOP_K}, sweeping ef_search x iterative_scan ({N_RUNS} runs each)\n")

    query_embedding = embedder.embed_query(QUERY)

    async with async_session_maker() as db:
        natural_plan = await explain_plan(db, document_id, query_embedding)
        print("--- Natural query plan (planner's own choice) ---")
        print(natural_plan)
        print("\n--- Natural sweep (GUCs apply only if the plan above uses the HNSW index) ---")
        natural_results = await sweep(db, document_id, query_embedding)

    # Force the documented pgvector failure mode: drop the competing
    # document_id B-tree index for this transaction only (never committed,
    # so it's always restored — even on a crash, since it's never applied),
    # and disable seq scan too — at this corpus's real size a full seq scan
    # is *also* cheaper than the approximate HNSW index (confirmed: with
    # only the B-tree dropped, the planner fell back to Seq Scan, not
    # HNSW). Only with both exact paths off does HNSW become the plan.
    async with async_session_maker() as db:
        await db.execute(text(f"DROP INDEX {FILTER_INDEX_NAME}"))
        await db.execute(text("SET LOCAL enable_seqscan = off"))
        forced_plan = await explain_plan(db, document_id, query_embedding)
        print(
            f"\n--- Forced-HNSW query plan ({FILTER_INDEX_NAME} dropped for this session only) ---"
        )
        print(forced_plan)
        print("\n--- Forced-HNSW sweep ---")
        forced_results = await sweep(db, document_id, query_embedding)
        await db.rollback()

    async with async_session_maker() as db:
        restored = await db.execute(
            text(f"SELECT indexname FROM pg_indexes WHERE indexname = '{FILTER_INDEX_NAME}'")
        )
        assert restored.first() is not None, f"{FILTER_INDEX_NAME} was not restored after rollback!"
    print(f"\n{FILTER_INDEX_NAME} confirmed restored after rollback.")

    output_path = Path("/app/data/filtering_benchmark.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(
            {
                "document_id": document_id,
                "document_selectivity": selectivity,
                "total_chunks": total_chunks,
                "chunks_in_document": n_chunks,
                "query": QUERY,
                "requested_top_k": TOP_K,
                "natural_plan": natural_plan,
                "natural_results": natural_results,
                "forced_hnsw_plan": forced_plan,
                "forced_hnsw_results": forced_results,
            },
            indent=2,
        )
    )
    print(f"\nSaved to {output_path}")


if __name__ == "__main__":
    asyncio.run(main())
