"""Mine reranker training pairs from the golden set + feedback corrections
(SPEC.md §3.5).

Positives come from golden-set items whose expected document is known, so the
label is independent evidence rather than the retriever agreeing with itself.
Hard negatives are the chunks the *current* pipeline ranks highly but which
belong to the wrong document - exactly the confusions the deployed model
actually makes.

Run inside the container:
  docker compose exec -e PYTHONPATH=/app api python scripts/mine_training_pairs.py
"""

import asyncio
from pathlib import Path

from sqlalchemy import delete, func, select

from app.db.session import async_session_maker
from app.evals.runner import load_golden_set
from app.learning.mining import build_pairs_from_golden_set, pairs_from_feedback
from app.models.learning import TrainingPair
from app.providers.embeddings.bge_small import get_embedding_provider

# Train split only, never full.jsonl: the held-out split is what the A/B
# promotion gate scores, so mining from it would train the candidate on its
# own exam (scripts/split_golden_set.py).
GOLDEN_PATH = Path("/app/eval-datasets/v1/train.jsonl")


async def main() -> None:
    embedder = get_embedding_provider()
    items = load_golden_set(GOLDEN_PATH)
    # Only answerable items carry an expected document to anchor a positive.
    answerable = [i for i in items if i.expected_arxiv_ids]
    print(f"Loaded {len(items)} golden items ({len(answerable)} answerable with expected docs)")

    async with async_session_maker() as db:
        # Re-mining is idempotent by design: negatives depend on the *current*
        # ranker, so stale pairs would train the next model against confusions
        # its predecessor already fixed.
        stale = (
            await db.execute(
                select(func.count(TrainingPair.id)).where(
                    TrainingPair.source.in_(("mined", "feedback"))
                )
            )
        ).scalar_one()
        if stale:
            await db.execute(
                delete(TrainingPair).where(TrainingPair.source.in_(("mined", "feedback")))
            )
            print(f"Cleared {stale} previously-mined pairs")

        mined = await build_pairs_from_golden_set(db, embedder, answerable)
        print(f"Mined {len(mined)} pairs from the golden set")

        from_feedback = await pairs_from_feedback(db, embedder)
        print(f"Mined {len(from_feedback)} pairs from feedback corrections")

        for pair in mined + from_feedback:
            db.add(pair)
        await db.commit()

        total = (await db.execute(select(func.count(TrainingPair.id)))).scalar_one()
        n_negatives = sum(len(p.hard_negative_chunk_ids) for p in mined + from_feedback)
        print(
            f"\nStored {len(mined) + len(from_feedback)} pairs "
            f"({n_negatives} hard negatives) - {total} total in table"
        )
        n_examples = len(mined + from_feedback) + n_negatives
        print(f"Cross-encoder training examples this yields: {n_examples}")


if __name__ == "__main__":
    asyncio.run(main())
