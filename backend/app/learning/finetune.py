import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.chunks import Chunk
from app.models.learning import ModelRegistry, TrainingPair

logger = logging.getLogger(__name__)

ARTIFACT_ROOT = Path("/app/data/models")


async def load_training_examples(db: AsyncSession, limit: int | None = None) -> list[tuple]:
    """Materialize training pairs into (query, chunk_text, label) rows for a
    cross-encoder: label 1.0 for the positive, 0.0 for each hard negative.

    Cross-encoders train on scored (query, passage) *pairs*, not triplets -
    so one TrainingPair row fans out into 1 positive + N negative examples.
    """
    stmt = select(TrainingPair).order_by(TrainingPair.created_at.desc())
    if limit is not None:
        stmt = stmt.limit(limit)
    pairs = list((await db.execute(stmt)).scalars().all())
    if not pairs:
        return []

    chunk_ids: set[uuid.UUID] = set()
    for pair in pairs:
        chunk_ids.add(pair.positive_chunk_id)
        for negative in pair.hard_negative_chunk_ids:
            try:
                chunk_ids.add(uuid.UUID(negative))
            except (ValueError, AttributeError):
                continue

    rows = (await db.execute(select(Chunk.id, Chunk.content).where(Chunk.id.in_(chunk_ids)))).all()
    text_by_id = {chunk_id: content for chunk_id, content in rows}

    examples: list[tuple] = []
    for pair in pairs:
        positive_text = text_by_id.get(pair.positive_chunk_id)
        if not positive_text:
            continue
        examples.append((pair.query, positive_text, 1.0))
        for negative in pair.hard_negative_chunk_ids:
            try:
                negative_text = text_by_id.get(uuid.UUID(negative))
            except (ValueError, AttributeError):
                continue
            if negative_text:
                examples.append((pair.query, negative_text, 0.0))
    return examples


def train_reranker(
    examples: list[tuple], base_model: str, output_dir: Path, epochs: int = 1, batch_size: int = 16
) -> dict:
    """Fine-tune a CrossEncoder on (query, passage, label) examples.

    Imports are function-local: `sentence_transformers`' training stack pulls
    in a large dependency graph that the API process has no reason to load
    just to serve a query - only the Celery worker running this ever needs it.
    """
    import torch
    from sentence_transformers import CrossEncoder, InputExample
    from torch.utils.data import DataLoader

    settings = get_settings()
    torch.set_num_threads(settings.FINETUNE_TORCH_THREADS)

    model = CrossEncoder(base_model, num_labels=1, device="cpu", max_length=256)
    train_examples = [InputExample(texts=[q, p], label=label) for q, p, label in examples]
    # sentence-transformers' InputExample list is a valid torch Dataset at
    # runtime (it implements __len__/__getitem__) but isn't typed as one.
    loader: DataLoader = DataLoader(
        train_examples,  # type: ignore[arg-type]
        shuffle=True,
        batch_size=batch_size,
    )

    started = datetime.now(UTC)
    model.fit(
        train_dataloader=loader,
        epochs=epochs,
        warmup_steps=max(1, len(loader) // 10),
        optimizer_params={"lr": 2e-5},
        show_progress_bar=False,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    model.save(str(output_dir))
    elapsed = (datetime.now(UTC) - started).total_seconds()

    return {
        "base_model": base_model,
        "n_examples": len(examples),
        "epochs": epochs,
        "batch_size": batch_size,
        "train_seconds": round(elapsed, 1),
        "artifact_path": str(output_dir),
    }


async def register_candidate(
    db: AsyncSession, kind: str, base_model: str, artifact_path: str, train_config: dict
) -> ModelRegistry:
    """Record a freshly-trained model as a *candidate*.

    Never 'active': a model earns promotion only by winning a measured A/B
    (SPEC.md §3.5), and writing it straight to active here would let a
    training run silently become production without ever being evaluated.
    """
    candidate = ModelRegistry(
        kind=kind,
        base_model=base_model,
        artifact_path=artifact_path,
        train_config=train_config,
        status="candidate",
    )
    db.add(candidate)
    await db.commit()
    await db.refresh(candidate)
    return candidate
