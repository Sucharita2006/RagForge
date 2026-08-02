from app.evals.judge import parse_judge_scores


def test_parse_judge_scores_extracts_all_fields() -> None:
    text = (
        "FAITHFULNESS: 0.9\n"
        "ANSWER_CORRECTNESS: 0.75\n"
        "CONTEXT_PRECISION: 0.5\n"
        "CONTEXT_RECALL: 1.0\n"
        "RATIONALE: The answer is well grounded but slightly incomplete."
    )
    scores = parse_judge_scores(text)
    assert scores["faithfulness"] == 0.9
    assert scores["answer_correctness"] == 0.75
    assert scores["context_precision"] == 0.5
    assert scores["context_recall"] == 1.0
    assert scores["rationale"] == "The answer is well grounded but slightly incomplete."


def test_parse_judge_scores_clamps_out_of_range_values() -> None:
    text = (
        "FAITHFULNESS: 1.5\nANSWER_CORRECTNESS: -0.2\nCONTEXT_PRECISION: 0.5\nCONTEXT_RECALL: 0.5"
    )
    scores = parse_judge_scores(text)
    assert scores["faithfulness"] == 1.0
    assert scores["answer_correctness"] == 0.0


def test_parse_judge_scores_missing_field_is_none() -> None:
    text = "FAITHFULNESS: 0.8\nCONTEXT_PRECISION: 0.5\nCONTEXT_RECALL: 0.5"
    scores = parse_judge_scores(text)
    assert scores["faithfulness"] == 0.8
    assert scores["answer_correctness"] is None


def test_parse_judge_scores_empty_text_is_all_none() -> None:
    scores = parse_judge_scores("")
    assert scores["faithfulness"] is None
    assert scores["rationale"] is None
