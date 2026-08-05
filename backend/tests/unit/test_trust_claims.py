import uuid

from app.generation.schemas import ClaimOut
from app.models.chunks import Chunk
from app.trust.claims import verify_claims


class FakeMiniCheck:
    def __init__(self, scores: list[float]) -> None:
        self._scores = scores

    def score(self, claims: list[str], docs: list[str]) -> list[float]:
        return self._scores


class BrokenMiniCheck:
    def score(self, claims: list[str], docs: list[str]) -> list[float]:
        raise RuntimeError("model failed")


def make_chunk(chunk_id: uuid.UUID, content: str) -> Chunk:
    return Chunk(
        id=chunk_id,
        document_id=uuid.uuid4(),
        content=content,
        token_count=10,
        content_hash="x" * 64,
        embedding=[0.0] * 384,
        embedding_model="fake",
    )


def test_verify_claims_scores_against_its_cited_chunk() -> None:
    chunk_id = uuid.uuid4()
    chunk = make_chunk(chunk_id, "Paris is the capital of France.")
    claim = ClaimOut(text="Paris is the capital.", citations=[str(chunk_id)])
    result = verify_claims(FakeMiniCheck([0.9]), [claim], [chunk])
    assert result[0].support_prob == 0.9
    assert result[0].verdict == "supported"


def test_verify_claims_falls_back_to_all_chunks_when_uncited() -> None:
    chunk = make_chunk(uuid.uuid4(), "some content")
    claim = ClaimOut(text="an uncited claim", citations=[])
    result = verify_claims(FakeMiniCheck([0.2]), [claim], [chunk])
    assert result[0].verdict == "unsupported"


def test_verify_claims_empty_claims_returns_empty_without_calling_minicheck() -> None:
    assert verify_claims(BrokenMiniCheck(), [], []) == []


def test_verify_claims_degrades_gracefully_on_minicheck_failure() -> None:
    claim = ClaimOut(text="x", citations=[])
    result = verify_claims(BrokenMiniCheck(), [claim], [])
    assert result[0].verdict == "unscored"
    assert result[0].support_prob is None
