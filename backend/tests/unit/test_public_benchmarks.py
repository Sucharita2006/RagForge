"""Scoring for the public benchmarks. A metric that differs from the
published definition makes every number it produces incomparable, so the
definitions are pinned here. No network or database."""

import math

from app.evals.retrieval_metrics import graded_ndcg_at_k, recall_at_k
from app.retrieval.dense import feedback_query
from scripts.beir import golden_items, orderings, split_of
from scripts.scifact_checker import (
    CONTRADICT,
    NEI,
    SUPPORT,
    auroc,
    balanced_accuracy,
    build_pairs,
    summarize,
)


def test_graded_ndcg_uses_the_grade_as_gain_and_counts_a_document_once() -> None:
    relevance = {"a": 2, "b": 1}
    assert graded_ndcg_at_k(["a", "b"], relevance, 10) == 1.0
    # b first, then a, then a again: (1/log2(2) + 2/log2(3)) / (2/log2(2) + 1/log2(3))
    expected = (1 + 2 / math.log2(3)) / (2 + 1 / math.log2(3))
    assert math.isclose(graded_ndcg_at_k(["b", "a", "a"], relevance, 10), expected)
    assert graded_ndcg_at_k(["x"], {}, 10) == 0.0


def test_recall_counts_relevant_documents_inside_the_cutoff() -> None:
    relevance = {"a": 1, "b": 2, "c": 0}
    assert recall_at_k(["a", "x", "b"], relevance, 2) == 0.5
    assert recall_at_k(["a", "b"], relevance, 10) == 1.0


def test_beir_golden_set_keeps_judged_questions_with_a_positive_grade() -> None:
    queries = {"q1": "first", "q2": "second", "q3": "third"}
    judgments = {"q1": {"d1": 1, "d2": 0}, "q2": {"d3": 0}, "q4": {"d4": 1}}
    items = golden_items(queries, judgments)
    assert items == [
        {
            "id": "q1",
            "type": "beir",
            "question": "first",
            "expected_arxiv_ids": ["d1"],
            "relevance": {"d1": 1},
        }
    ]


def test_ordering_policies() -> None:
    # id, dense rank, sparse rank, RRF, rerank; stored in reranked order
    pool = [
        ["c", 3, None, 0.010, 2.5],
        ["a", 1, 2, 0.030, -1.0],
        ["s", None, 1, 0.016, -2.0],
        ["b", 2, None, 0.015, -3.0],
    ]
    orders = orderings(pool, thresholds=[0.0, 3.0])
    assert orders["reranked"] == ["c", "a", "s", "b"]
    assert orders["returned"] == ["c", "a", "s", "b"]  # the stored order, as the pipeline gave it
    assert orders["dense"] == ["a", "b", "c"]
    assert orders["fused"] == ["a", "s", "b", "c"]
    # only "c" clears 0.0, so it is lifted and the rest keep the dense order
    assert orders["lift(dense,+0.0)"] == ["c", "a", "b"]
    assert orders["lift(fused,+3.0)"] == orders["fused"]
    # the best rerank score (2.5) clears 0.0 but not 3.0
    assert orders["gate(fused,+0.0)"] == orders["reranked"]
    assert orders["gate(fused,+3.0)"] == orders["fused"]


def test_feedback_query_moves_toward_the_centroid_and_stays_unit_length() -> None:
    query = [1.0, 0.0]
    assert feedback_query(query, [], 1.0) == query
    assert feedback_query(query, [[0.0, 1.0]], 0.0) == query
    # weight 1 toward (0, 1): (1, 1) normalised
    moved = feedback_query(query, [[0.0, 1.0], [0.0, 1.0]], 1.0)
    assert math.isclose(moved[0], moved[1]) and math.isclose(math.hypot(*moved), 1.0)


def test_dev_test_split_is_stable_and_about_thirty_percent() -> None:
    assert split_of("q1") == split_of("q1")
    dev = sum(split_of(f"q{i}") == "dev" for i in range(2000))
    assert 500 < dev < 700


def test_scifact_pairs_take_the_evidence_label_or_not_enough_info() -> None:
    corpus = {
        1: {"title": "T1", "abstract": ["A.", "B."]},
        2: {"title": "T2", "abstract": ["C."]},
    }
    claims = [
        {"id": 7, "claim": "X", "evidence": {"1": [{"label": "CONTRADICT"}]}, "cited_doc_ids": [1]},
        {"id": 8, "claim": "Y", "evidence": {}, "cited_doc_ids": [2, 99]},
    ]
    pairs = build_pairs(claims, corpus)
    assert [(p.claim_id, p.doc_id, p.label) for p in pairs] == [(7, 1, CONTRADICT), (8, 2, NEI)]
    assert pairs[0].premise == "T1\nA. B."


def test_checker_metrics() -> None:
    assert auroc([0.9, 0.8], [0.1, 0.8]) == (1 + 1 + 1 + 0.5) / 4
    labels = [SUPPORT, SUPPORT, CONTRADICT, NEI]
    assert balanced_accuracy(labels, [True, False, False, True]) == (0.5 + 0.5) / 2

    summary = summarize(labels, [0.9, 0.2, 0.1, 0.7], threshold=0.5)
    assert summary["pairs"] == 4
    assert summary["judged_supported_by_label"][SUPPORT]["mean"] == 0.5
    assert summary["precision_of_supported"]["mean"] == 0.5
    # supported probs (0.9, 0.2) against the rest (0.1, 0.7): three of four pairs ordered right
    assert summary["auroc"]["mean"] == (1 + 1 + 1 + 0) / 4
