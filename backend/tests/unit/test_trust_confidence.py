import uuid

from app.models.chunks import Chunk
from app.retrieval.fusion import FusedCandidate
from app.trust.confidence import compute_confidence
from app.trust.schemas import VerifiedClaim


def make_candidate(rerank_score: float) -> FusedCandidate:
    chunk = Chunk(
        id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        content="x",
        token_count=10,
        content_hash="x" * 64,
        embedding=[0.0] * 384,
        embedding_model="fake",
    )
    return FusedCandidate(chunk=chunk, rrf_score=0.0, rerank_score=rerank_score)


def test_compute_confidence_zero_when_insufficient_context() -> None:
    assert compute_confidence([], [], insufficient_context=True) == 0.0


def test_compute_confidence_zero_when_no_claims() -> None:
    assert compute_confidence([], [make_candidate(5.0)], insufficient_context=False) == 0.0


def test_compute_confidence_high_when_well_supported_and_cited() -> None:
    claims = [VerifiedClaim(text="a", citations=["c1"], support_prob=0.95, verdict="supported")]
    candidates = [make_candidate(5.0), make_candidate(4.0)]
    confidence = compute_confidence(claims, candidates, insufficient_context=False)
    assert confidence > 0.7


def test_compute_confidence_low_when_unsupported_and_uncited() -> None:
    claims = [VerifiedClaim(text="a", citations=[], support_prob=0.05, verdict="unsupported")]
    candidates = [make_candidate(-5.0)]
    confidence = compute_confidence(claims, candidates, insufficient_context=False)
    assert confidence < 0.3


def test_compute_confidence_unscored_claim_counts_as_zero_support() -> None:
    claims = [VerifiedClaim(text="a", citations=["c1"], support_prob=None, verdict="unscored")]
    confidence = compute_confidence(claims, [make_candidate(0.0)], insufficient_context=False)
    assert confidence < 0.5


def test_compute_confidence_no_rerank_scores_treated_as_zero_retrieval_strength() -> None:
    claims = [VerifiedClaim(text="a", citations=["c1"], support_prob=1.0, verdict="supported")]
    candidates = [FusedCandidate(chunk=make_candidate(0.0).chunk, rrf_score=0.0, rerank_score=None)]
    confidence = compute_confidence(claims, candidates, insufficient_context=False)
    # 0.5*1.0 (claim_support) + 0.3*0.0 (no rerank score) + 0.2*1.0 (cited) = 0.7
    assert abs(confidence - 0.7) < 1e-9
