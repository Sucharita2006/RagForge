import json
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.evals.schemas import GoldenItem
from app.generation.generator import generate_answer
from app.providers.embeddings.base import EmbeddingProvider
from app.providers.llm.base import LLMProvider
from app.retrieval.assembly import assemble_context, expand_to_parents
from app.retrieval.pipeline import retrieve as run_retrieval_pipeline
from app.trust.claims import verify_claims
from app.trust.confidence import compute_confidence
from app.trust.minicheck import MiniCheckProvider


def load_calibration_set(path: Path) -> list[GoldenItem]:
    return [
        GoldenItem(**json.loads(line)) for line in path.read_text().splitlines() if line.strip()
    ]


async def compute_calibration_confidences(
    db: AsyncSession,
    items: list[GoldenItem],
    embedder: EmbeddingProvider,
    llm: LLMProvider,
    minicheck: MiniCheckProvider,
) -> list[tuple[GoldenItem, float]]:
    """Runs the full retrieve -> generate -> verify pipeline for every
    calibration item and returns each item's raw confidence score, computed
    with no threshold applied (SPEC.md §8.5: thresholds are swept
    afterward against these same scores, not recomputed per threshold)."""
    settings = get_settings()
    scored: list[tuple[GoldenItem, float]] = []
    for item in items:
        query_embedding = embedder.embed_query(item.question)
        fused = await run_retrieval_pipeline(db, item.question, query_embedding)
        top_candidates = fused[: settings.FINAL_TOP_K]
        expanded = await expand_to_parents(db, [c.chunk for c in top_candidates])
        context, used_chunks = assemble_context(expanded, settings.MAX_CONTEXT_TOKENS)
        valid_chunk_ids = {str(c.id) for c in used_chunks}
        answer, _ = await generate_answer(llm, item.question, context, valid_chunk_ids)
        verified = verify_claims(minicheck, answer.answer_sentences, used_chunks)
        confidence = compute_confidence(verified, top_candidates, answer.insufficient_context)
        scored.append((item, confidence))
    return scored


def sweep_thresholds(
    scored_items: list[tuple[GoldenItem, float]], n_steps: int = 101
) -> list[dict]:
    """Coverage / answered-precision at each of `n_steps` evenly spaced
    thresholds in [0, 1] (SPEC.md §8.5). "Answered" = confidence >= threshold
    (should_abstain's complement); "correct" among answered = item was
    actually answerable, matching the eval harness's answered_precision
    definition (app/evals/runner.py) for consistency."""
    curve = []
    for i in range(n_steps):
        threshold = i / (n_steps - 1)
        answered = [(item, conf) for item, conf in scored_items if conf >= threshold]
        coverage = len(answered) / len(scored_items) if scored_items else 0.0
        correct = sum(1 for item, _ in answered if not item.unanswerable)
        precision = correct / len(answered) if answered else 1.0
        curve.append(
            {"threshold": threshold, "coverage": coverage, "answered_precision": precision}
        )
    return curve


def choose_threshold(curve: list[dict], target_precision: float) -> float:
    """Lowest threshold meeting >= target_precision, maximizing coverage
    subject to the precision floor (SPEC.md §8.5: "pick the lowest threshold
    meeting >=0.90 precision"). `curve` must be threshold-ascending. Falls
    back to 1.0 (abstain on everything) if nothing in the swept range
    meets the target - a real, informative outcome, not an error."""
    for point in curve:
        if point["answered_precision"] >= target_precision:
            return point["threshold"]
    return 1.0
