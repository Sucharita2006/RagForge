import math

from app.config import get_settings
from app.retrieval.fusion import FusedCandidate
from app.trust.schemas import VerifiedClaim


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def compute_confidence(
    verified_claims: list[VerifiedClaim],
    used_candidates: list[FusedCandidate],
    insufficient_context: bool,
) -> float:
    """SPEC.md §3.3 weighted confidence: claim support (0.5) + retrieval
    strength (0.3) + generator sufficiency (0.2).

    - claim support: mean MiniCheck support_prob across claims (unscored
      claims count as 0 - a claim that couldn't be checked isn't confirmed).
    - retrieval strength: mean sigmoid(rerank_score) of the chunks actually
      used, since the MiniLM cross-encoder's raw scores are unbounded
      logits, not probabilities (SPEC.md §7.1 reranker choice).
    - sufficiency: SPEC.md leaves this "judge-free heuristics" undefined in
      detail; interpreted here as the fraction of claims that cite at least
      one chunk (a claim can be true prose but ungrounded to any specific
      span - that's a distinct signal from whether the *cited* span
      actually entails it, which claim support already covers).
    """
    settings = get_settings()
    if insufficient_context or not verified_claims:
        return 0.0

    claim_support = sum(c.support_prob or 0.0 for c in verified_claims) / len(verified_claims)

    rerank_scores = [c.rerank_score for c in used_candidates if c.rerank_score is not None]
    retrieval_strength = (
        sum(_sigmoid(s) for s in rerank_scores) / len(rerank_scores) if rerank_scores else 0.0
    )

    sufficiency = sum(1 for c in verified_claims if c.citations) / len(verified_claims)

    return (
        settings.CONFIDENCE_WEIGHT_CLAIM_SUPPORT * claim_support
        + settings.CONFIDENCE_WEIGHT_RETRIEVAL * retrieval_strength
        + settings.CONFIDENCE_WEIGHT_SUFFICIENCY * sufficiency
    )
