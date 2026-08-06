import logging
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.answers import Answer
from app.models.chunks import Chunk
from app.models.documents import Document
from app.models.learning import FailureCluster, Feedback
from app.models.queries import Query

logger = logging.getLogger(__name__)

# SPEC.md §5's four cluster labels, each with the action it implies.
_ACTIONS = {
    "retrieval_miss": "Mine these queries as hard negatives and re-train the reranker.",
    "generation_error": "Review the generation prompt; the context was retrieved but misused.",
    "parsing_gap": "Re-ingest the affected documents; parsing likely lost the relevant content.",
    "knowledge_gap": "The corpus lacks an answer - ingest source material covering these topics.",
}


def classify_failure(
    abstained: bool, has_citations: bool, corpus_has_candidates: bool, parser_fallback: bool
) -> str:
    """Bucket one failure into SPEC.md §5's four labels.

    Ordering matters and encodes the diagnosis: if nothing plausible was
    retrievable at all, it's a *knowledge* gap regardless of what the
    generator then did; if the corpus did have candidates but a document
    fell back to a lossy parser, suspect *parsing* before blaming retrieval;
    only then is an abstention a retrieval miss, and an answer without
    citations a generation error.
    """
    if not corpus_has_candidates:
        return "knowledge_gap"
    if parser_fallback:
        return "parsing_gap"
    if abstained:
        return "retrieval_miss"
    if not has_citations:
        return "generation_error"
    return "generation_error"


async def cluster_recent_failures(
    db: AsyncSession, window_hours: int = 168
) -> list[FailureCluster]:
    """Group recent failures (thumbs-down, or abstentions) into labelled
    clusters with a suggested action (SPEC.md §3.9 page 8).

    Failure signal comes from two places deliberately: explicit negative
    feedback (the user said it was wrong) and abstentions (the system said
    it couldn't answer). Both are failures worth acting on, and a system
    that only counted the former would under-report by exactly the amount
    its trust layer was working.
    """
    since = datetime.now(UTC) - timedelta(hours=window_hours)
    window_label = f"{window_hours}h"

    downvoted_ids = set(
        (
            await db.execute(
                select(Feedback.answer_id).where(Feedback.rating < 0, Feedback.created_at >= since)
            )
        )
        .scalars()
        .all()
    )

    rows = (
        await db.execute(
            select(Answer, Query)
            .join(Query, Query.id == Answer.query_id)
            .where(Answer.created_at >= since)
        )
    ).all()

    failures = [(a, q) for a, q in rows if a.id in downvoted_ids or a.abstained]
    if not failures:
        return []

    # Resolve, per failing answer, whether any chunk it cited came from a
    # document that fell back to the lossy parser - batched, since this runs
    # over a whole window of answers.
    cited_chunk_ids: set[uuid.UUID] = set()
    per_answer_chunks: dict[uuid.UUID, set[uuid.UUID]] = {}
    for answer, _ in failures:
        ids: set[uuid.UUID] = set()
        for claim in answer.claims or []:
            for citation in claim.get("citations", []):
                try:
                    ids.add(uuid.UUID(citation))
                except (ValueError, AttributeError):
                    continue
        per_answer_chunks[answer.id] = ids
        cited_chunk_ids |= ids

    doc_by_chunk: dict[uuid.UUID, uuid.UUID] = {}
    if cited_chunk_ids:
        chunk_rows = (
            await db.execute(
                select(Chunk.id, Chunk.document_id).where(Chunk.id.in_(cited_chunk_ids))
            )
        ).all()
        doc_by_chunk = {chunk_id: document_id for chunk_id, document_id in chunk_rows}
    fallback_docs = set(
        (await db.execute(select(Document.id).where(Document.parser != "docling"))).scalars().all()
    )

    grouped: dict[str, list[str]] = {}
    for answer, query in failures:
        claims = answer.claims or []
        answer_docs = {doc_by_chunk[c] for c in per_answer_chunks[answer.id] if c in doc_by_chunk}
        label = classify_failure(
            abstained=bool(answer.abstained),
            has_citations=any(c.get("citations") for c in claims),
            # An abstention with zero claims and zero confidence is the
            # signature of "nothing relevant existed", not "ranked wrong".
            corpus_has_candidates=bool(claims) or (answer.confidence or 0.0) > 0.0,
            parser_fallback=bool(answer_docs & fallback_docs),
        )
        grouped.setdefault(label, []).append(str(query.id))

    clusters = [
        FailureCluster(
            window=window_label,
            cluster_label=label,
            size=len(query_ids),
            sample_query_ids=query_ids[:10],
            suggested_action=_ACTIONS[label],
        )
        for label, query_ids in sorted(grouped.items())
    ]
    for cluster in clusters:
        db.add(cluster)
    await db.commit()
    return clusters
