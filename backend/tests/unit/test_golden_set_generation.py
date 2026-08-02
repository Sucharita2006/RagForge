from scripts.generate_golden_set import _looks_like_references, _parse_question_answer


def test_parse_question_answer_extracts_both_fields() -> None:
    text = "QUESTION: What is X?\nANSWER: X is Y."
    question, answer = _parse_question_answer(text)
    assert question == "What is X?"
    assert answer == "X is Y."


def test_parse_question_answer_question_only_format() -> None:
    text = "QUESTION: What is X?"
    question, answer = _parse_question_answer(text)
    assert question == "What is X?"
    assert answer is None


def test_parse_question_answer_falls_back_to_raw_text_without_marker() -> None:
    question, answer = _parse_question_answer("just some unstructured text")
    assert question == "just some unstructured text"
    assert answer is None


def test_looks_like_references_flags_multiple_urls() -> None:
    content = "See http://a.example.com and also http://b.example.com for details."
    assert _looks_like_references(content) is True


def test_looks_like_references_flags_author_list_pattern() -> None:
    content = (
        "Smith, J. and Doe, A. Some title. Kale, S. and Chandel, R. Another title. "
        "Pal, D. K. and Joshi, A. Yet another title."
    )
    assert _looks_like_references(content) is True


def test_looks_like_references_does_not_flag_normal_prose() -> None:
    content = (
        "This paper proposes a novel retrieval-augmented generation approach "
        "that combines dense and sparse retrieval to improve answer quality."
    )
    assert _looks_like_references(content) is False
