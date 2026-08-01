from app.config import get_settings
from app.providers.llm.base import LLMProvider

ENRICHMENT_SYSTEM_PROMPT = (
    "You situate a chunk of text within its source document for search "
    "retrieval. Given the parent section and a specific chunk from within "
    "it, write ONE concise sentence (at most 100 tokens) describing what "
    "the chunk is and where it sits in the document — e.g. 'This chunk is "
    "from <doc>, section <X>, and discusses ...'. Respond with ONLY that "
    "sentence, nothing else."
)


def enrichment_enabled() -> bool:
    """Feature-flagged AND requires a key (DECISIONS.md 2026-07-30) — the
    free-tier Gemini key is reserved for judge/testset-gen/enrichment only,
    and is optional. Without a key this always returns False regardless of
    CONTEXTUAL_ENRICHMENT, so ingestion behaves identically to Phase 1 until
    a key is provided."""
    settings = get_settings()
    return settings.CONTEXTUAL_ENRICHMENT and bool(settings.GOOGLE_API_KEY)


def build_enrichment_prompt(document_title: str, parent_content: str, chunk_content: str) -> str:
    # Parent content capped to keep the enrichment call itself cheap/fast —
    # it only needs enough surrounding context to situate the chunk, not the
    # full parent verbatim.
    return (
        f"Document: {document_title}\n\n"
        f"Parent section:\n{parent_content[:2000]}\n\n"
        f"Chunk:\n{chunk_content}\n\n"
        "Situating sentence:"
    )


async def generate_context_prefix(
    llm: LLMProvider, document_title: str, parent_content: str, chunk_content: str
) -> str:
    prompt = build_enrichment_prompt(document_title, parent_content, chunk_content)
    result = await llm.generate(ENRICHMENT_SYSTEM_PROMPT, prompt)
    return result["text"].strip()[:500]  # safety cap regardless of the ≤100-token instruction
