from app.generation.parser import parse_answer

VALID_IDS = {"chunk-a", "chunk-b"}


def test_parse_answer_extracts_citations_per_sentence() -> None:
    text = "The sky is blue. [chunk_id=chunk-a] Grass is green. [chunk_id=chunk-b]"
    answer = parse_answer(text, VALID_IDS)
    assert not answer.insufficient_context
    assert len(answer.answer_sentences) == 2
    assert answer.answer_sentences[0].text == "The sky is blue."
    assert answer.answer_sentences[0].citations == ["chunk-a"]
    assert answer.answer_sentences[1].citations == ["chunk-b"]


def test_parse_answer_drops_citations_to_unknown_chunk_ids() -> None:
    """A local model can fabricate a plausible-looking chunk_id instead of
    copying a real one from context (DECISIONS.md 2026-07-31) — citations to
    ids never in the context must not pass through."""
    text = "A fact with a fabricated source. [chunk_id=not-a-real-chunk]"
    answer = parse_answer(text, VALID_IDS)
    assert answer.answer_sentences[0].citations == []
    assert answer.answer_sentences[0].text == "A fact with a fabricated source."


def test_parse_answer_detects_insufficient_context_marker() -> None:
    text = "I don't have enough grounded information to answer this question."
    answer = parse_answer(text, VALID_IDS)
    assert answer.insufficient_context
    assert answer.answer_sentences == []


def test_parse_answer_multiple_citations_on_one_sentence() -> None:
    text = "Both sources agree. [chunk_id=chunk-a][chunk_id=chunk-b]"
    answer = parse_answer(text, VALID_IDS)
    assert answer.answer_sentences[0].citations == ["chunk-a", "chunk-b"]


def test_parse_answer_empty_text_is_insufficient() -> None:
    answer = parse_answer("", VALID_IDS)
    assert answer.insufficient_context
    assert answer.answer_sentences == []
