import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.answers import Answer
from app.models.documents import Document
from app.models.learning import Feedback, TrainingPair
from app.models.queries import Query
from app.providers.embeddings.base import EmbeddingProvider
from app.retrieval.fusion import FusedCandidate
from app.retrieval.pipeline import retrieve as run_retrieval_pipeline

logger = logging.getLogger(__name__)


async def _external_ids_for(
    db: AsyncSession, candidates: list[FusedCandidate]
) -> dict[uuid.UUID, str | None]:
    """One batched lookup for every candidate's document external id.

    (Resolving these per-candidate inside the ranking loop is an N+1 against
    a query that runs for every training pair mined.)
    """
    document_ids = {c.chunk.document_id for c in candidates}
    if not document_ids:
        return {}
    rows = (
        await db.execute(
            select(Document.id, Document.external_id).where(Document.id.in_(document_ids))
        )
    ).all()
    return {doc_id: external_id for doc_id, external_id in rows}


async def mine_hard_negatives(
    db: AsyncSession,
    query: str,
    positive_chunk_id: uuid.UUID,
    embedder: EmbeddingProvider,
    max_negatives: int = 4,
) -> list[uuid.UUID]:
    """Hard negatives = chunks the *current* retriever ranks highly for this
    query but which are not the known-correct chunk (SPEC.md §3.5).

    "Hard" is the whole point: random negatives are trivially separable and
    teach a cross-encoder almost nothing. Mining against the live pipeline
    means the negatives are exactly the confusions the deployed model
    actually makes.
    """
    settings = get_settings()
    query_embedding = embedder.embed_query(query)
    candidates = await run_retrieval_pipeline(db, query, query_embedding)

    negatives: list[uuid.UUID] = []
    for candidate in candidates[: settings.RERANK_CANDIDATES]:
        if candidate.chunk.id == positive_chunk_id:
            continue
        negatives.append(candidate.chunk.id)
        if len(negatives) >= max_negatives:
            break
    return negatives


async def round_trip_check(
    db: AsyncSession, query: str, positive_chunk_id: uuid.UUID, embedder: EmbeddingProvider
) -> bool:
    """SPEC.md §3.5's filter for synthetic pairs: keep a generated (query,
    chunk) pair only if retrieving that query actually surfaces the chunk it
    was generated from.

    A generated question its own source chunk can't answer is either too
    vague or about something the chunk mentions only in passing - training
    on it teaches the model to retrieve the wrong thing.
    """
    query_embedding = embedder.embed_query(query)
    candidates = await run_retrieval_pipeline(db, query, query_embedding)
    top = candidates[: get_settings().FINAL_TOP_K]
    return any(c.chunk.id == positive_chunk_id for c in top)


async def pairs_from_feedback(
    db: AsyncSession, embedder: EmbeddingProvider, limit: int = 100
) -> list[TrainingPair]:
    """Mine training pairs from thumbs-down feedback (SPEC.md §3.5).

    A bare thumbs-down says "the chunks retrieved for this query were wrong"
    but does *not* say which chunk would have been right - so it yields hard
    negatives with no positive to pair them against, and a triple can't be
    formed. Rather than invent a positive (which would train the model on
    fabricated ground truth), only corrections are used: the correction text
    describes the right answer, so retrieving *with it* locates the chunk
    that actually contains it. Bare thumbs-down still feeds failure
    clustering, which is where an unlabelled negative signal genuinely belongs.
    """
    settings = get_settings()
    rows = (
        await db.execute(
            select(Feedback, Query.raw_text)
            .join(Answer, Answer.id == Feedback.answer_id)
            .join(Query, Query.id == Answer.query_id)
            .where(Feedback.rating < 0, Feedback.correction.isnot(None))
            .order_by(Feedback.created_at.desc())
            .limit(limit)
        )
    ).all()

    pairs: list[TrainingPair] = []
    for feedback, question in rows:
        try:
            correction = (feedback.correction or "").strip()
            if not correction or not question:
                continue

            # The correction describes the true answer - retrieve with it to
            # find the chunk that holds it, and use that as the positive.
            correction_hits = await run_retrieval_pipeline(
                db, correction, embedder.embed_query(correction)
            )
            if not correction_hits:
                continue
            positive_id = correction_hits[0].chunk.id

            # Negatives are what the *original question* wrongly surfaced.
            original_hits = await run_retrieval_pipeline(
                db, question, embedder.embed_query(question)
            )
            negatives = [
                c.chunk.id
                for c in original_hits[: settings.RERANK_CANDIDATES]
                if c.chunk.id != positive_id
            ][:4]
            if not negatives:
                continue

            pairs.append(
                TrainingPair(
                    query=question,
                    positive_chunk_id=positive_id,
                    hard_negative_chunk_ids=[str(n) for n in negatives],
                    source="feedback",
                )
            )
        except Exception:
            logger.exception("feedback pair mining failed for feedback %s", feedback.id)
    return pairs


async def build_pairs_from_golden_set(
    db: AsyncSession,
    embedder: EmbeddingProvider,
    items: list,
    max_negatives: int = 4,
) -> list[TrainingPair]:
    """Build (query, positive, hard-negatives) rows from golden-set items
    whose expected document is known.

    The positive is the top-ranked chunk belonging to the item's *expected*
    document - a chunk we have independent reason to believe is correct,
    rather than whatever the retriever happened to rank first (which would
    just teach the model to agree with itself).
    """
    settings = get_settings()
    pairs: list[TrainingPair] = []
    for item in items:
        if not item.expected_arxiv_ids:
            continue
        try:
            query_embedding = embedder.embed_query(item.question)
            candidates = await run_retrieval_pipeline(db, item.question, query_embedding)
            if not candidates:
                continue

            ranked = candidates[: settings.RERANK_CANDIDATES]
            external_by_doc = await _external_ids_for(db, ranked)
            expected = set(item.expected_arxiv_ids)

            positive_id: uuid.UUID | None = None
            negatives: list[uuid.UUID] = []
            for candidate in ranked:
                external_id = external_by_doc.get(candidate.chunk.document_id)
                if external_id in expected:
                    if positive_id is None:
                        positive_id = candidate.chunk.id
                elif len(negatives) < max_negatives:
                    negatives.append(candidate.chunk.id)

            if positive_id is None or not negatives:
                continue
            pairs.append(
                TrainingPair(
                    query=item.question,
                    positive_chunk_id=positive_id,
                    hard_negative_chunk_ids=[str(n) for n in negatives],
                    source="mined",
                )
            )
        except Exception:
            logger.exception("pair mining failed for item %s", getattr(item, "id", "?"))
    return pairs
