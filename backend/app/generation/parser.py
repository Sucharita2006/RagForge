import re

from app.generation.schemas import ClaimOut, GeneratedAnswer

_CITATION_PATTERN = re.compile(r"\[chunk_id=([^\]]+)\]")
# Captures any citation markers trailing a sentence's punctuation (even when
# separated from it by whitespace) so re.split's capture-group interleaving
# lets us reattach them to the sentence they trail, rather than the next one.
_SENTENCE_SPLIT_PATTERN = re.compile(r"(?<=[.!?])((?:\s*\[chunk_id=[^\]]+\])*)(?:\s+|$)")
_INSUFFICIENT_MARKER = "i don't have enough grounded information"


def _split_sentences(text: str) -> list[str]:
    """Split into sentences, keeping trailing citation markers attached to
    the sentence they follow. Local models place citations both immediately
    before *and* after the terminal punctuation (with or without a space) in
    practice — a naive `split on ". "` orphans the "after, with a space"
    case into its own citation-only fragment, which then gets silently
    dropped since it has no sentence text of its own (found by comparing
    constrained vs. real generation output — see DECISIONS.md 2026-07-31)."""
    parts = _SENTENCE_SPLIT_PATTERN.split(text)
    sentences = []
    for i in range(0, len(parts), 2):
        sentence = parts[i]
        if i + 1 < len(parts):
            sentence += parts[i + 1]
        sentences.append(sentence)
    return sentences


def parse_answer(text: str, valid_chunk_ids: set[str]) -> GeneratedAnswer:
    """Parse plain-prose model output (DECISIONS.md 2026-07-31) into the same
    GeneratedAnswer shape the rest of the app (DB storage, API response)
    expects, so callers don't care that generation stopped using Ollama's
    JSON-schema `format` constraint.

    Citations to a chunk_id not in valid_chunk_ids (i.e. never actually in
    the context sent to the model) are dropped — a cheap citation-ID hygiene
    check, not full claim verification against source content (that's
    Phase 4's NLI-based trust layer). Local models can and do fabricate a
    plausible-looking id instead of copying a real one from context.
    """
    text = text.strip()
    if _INSUFFICIENT_MARKER in text.lower():
        return GeneratedAnswer(answer_sentences=[], insufficient_context=True)

    claims: list[ClaimOut] = []
    for sentence in _split_sentences(text):
        sentence = sentence.strip()
        if not sentence:
            continue
        citations = [c for c in _CITATION_PATTERN.findall(sentence) if c in valid_chunk_ids]
        clean_text = _CITATION_PATTERN.sub("", sentence).strip()
        if clean_text:
            claims.append(ClaimOut(text=clean_text, citations=citations))

    return GeneratedAnswer(answer_sentences=claims, insufficient_context=len(claims) == 0)
