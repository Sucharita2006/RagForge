import logging

from app.config import get_settings
from app.generation.schemas import ClaimOut
from app.models.chunks import Chunk
from app.trust.minicheck import MiniCheckProvider
from app.trust.schemas import VerifiedClaim

logger = logging.getLogger(__name__)


def verify_claims(
    minicheck: MiniCheckProvider, claims: list[ClaimOut], used_chunks: list[Chunk]
) -> list[VerifiedClaim]:
    """SPEC.md §3.3: for each claim, run MiniCheck against the union of its
    cited chunks, falling back to every retrieved/used chunk when a claim
    carries no citations at all (still worth checking - a model can state a
    fact without citing it, and MiniCheck can still catch it as unsupported).
    """
    if not claims:
        return []

    chunks_by_id = {str(c.id): c for c in used_chunks}
    fallback_doc = "\n\n".join(c.content for c in used_chunks)
    docs = []
    for claim in claims:
        cited_content = [
            chunks_by_id[cid].content for cid in claim.citations if cid in chunks_by_id
        ]
        docs.append("\n\n".join(cited_content) if cited_content else fallback_doc)

    settings = get_settings()
    claim_texts = [c.text for c in claims]
    try:
        support_probs = minicheck.score(claims=claim_texts, docs=docs)
    except Exception:
        # a MiniCheck failure (e.g. model load issue) shouldn't 500 the
        # whole /query endpoint over an optional trust signal - degrade to
        # unscored rather than losing the answer entirely.
        logger.exception("MiniCheck scoring failed; claims left unscored")
        return [
            VerifiedClaim(text=c.text, citations=c.citations, support_prob=None, verdict="unscored")
            for c in claims
        ]

    verified = []
    for claim, prob in zip(claims, support_probs, strict=True):
        verdict = "supported" if prob >= settings.MINICHECK_SUPPORT_THRESHOLD else "unsupported"
        verified.append(
            VerifiedClaim(
                text=claim.text, citations=claim.citations, support_prob=prob, verdict=verdict
            )
        )
    return verified
