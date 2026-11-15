import uuid

from sqlalchemy import column, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chunks import Chunk

# Okapi BM25 (k1 = 1.2, b = 0.75, Lucene's non-negative idf) over the `tsv`
# column's English lexemes. A chunk is a candidate when it shares ANY lexeme
# with the query; term frequency is the lexeme's position count and document
# length is token_count.
#
# Replaces websearch_to_tsquery + ts_rank_cd (DECISIONS.md 2026-11-15). That
# pair required EVERY query term to be in a chunk, so a natural-language
# question matched almost nothing, and ts_rank_cd has no idf, so relaxing the
# match to OR ranked chunks by how often they said common words.
#
# ponytail: idf and avgdl are recomputed per query and every candidate's tsv
# is unnested, so cost grows with corpus size and query length (~0.1s at 8k
# chunks). Past ~100k chunks, move to a BM25 index extension (pg_textsearch,
# ParadeDB pg_search) rather than tuning this.
#
# MATERIALIZED is load-bearing: inlined, the planner re-ran the df count once
# per matched row (1,726 times on one NanoFiQA query: 2.0s instead of 0.1s).
_BM25_SQL = """
WITH stats AS MATERIALIZED (
    SELECT count(*)::float8 AS n, avg(token_count)::float8 AS avgdl
    FROM chunks WHERE NOT is_parent
), terms AS MATERIALIZED (
    SELECT lexeme, (
        SELECT count(*) FROM chunks
        WHERE NOT is_parent AND tsv @@ plainto_tsquery('simple', lexeme)
    )::float8 AS df
    FROM unnest(tsvector_to_array(to_tsvector('english', :query))) AS lexeme
)
SELECT c.id, sum(
    ln(1 + (stats.n - terms.df + 0.5) / (terms.df + 0.5))
    * cardinality(hit.positions) * 2.2
    / (cardinality(hit.positions) + 1.2 * (0.25 + 0.75 * c.token_count / stats.avgdl))
) AS score
FROM chunks c
CROSS JOIN stats
CROSS JOIN LATERAL unnest(c.tsv) AS hit(lexeme, positions, weights)
JOIN terms ON terms.lexeme = hit.lexeme
WHERE NOT c.is_parent
  AND c.tsv @@ replace(plainto_tsquery('english', :query)::text, '&', '|')::tsquery
  {document_filter}
GROUP BY c.id
ORDER BY score DESC, c.id
LIMIT :top_k
"""


async def sparse_search(
    db: AsyncSession, query_text: str, top_k: int, document_id: uuid.UUID | None = None
) -> list[tuple[Chunk, float]]:
    """BM25 over Postgres full-text lexemes (SPEC.md §3.2 step 4). Parent
    chunks are never search candidates (only children are embedded/searched -
    SPEC.md §3.2 step 7). idf is corpus-wide even under a document filter."""
    params: dict = {"query": query_text, "top_k": top_k}
    document_filter = ""
    if document_id is not None:
        document_filter = "AND c.document_id = :document_id"
        params["document_id"] = document_id
    bm25 = (
        text(_BM25_SQL.format(document_filter=document_filter))
        .columns(column("id"), column("score"))
        .subquery("bm25")
    )
    stmt = (
        select(Chunk, bm25.c.score)
        .join(bm25, Chunk.id == bm25.c.id)
        .order_by(bm25.c.score.desc(), Chunk.id)
    )
    result = await db.execute(stmt, params)
    return [(chunk, float(score)) for chunk, score in result.all()]
