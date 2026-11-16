import math


def hit_rate(ranked_ids: list[str], expected_ids: list[str]) -> float:
    """1.0 if ANY expected id appears anywhere in the ranked list, else 0.0.
    For multi-hop items (2 expected ids) this is deliberately an "any match"
    rule, same as single-hop - a stricter "all ids present" variant would
    need its own metric name to stay comparable across item types."""
    if not expected_ids:
        return 0.0
    expected = set(expected_ids)
    return 1.0 if any(doc_id in expected for doc_id in ranked_ids) else 0.0


def reciprocal_rank(ranked_ids: list[str], expected_ids: list[str]) -> float:
    expected = set(expected_ids)
    for i, doc_id in enumerate(ranked_ids, start=1):
        if doc_id in expected:
            return 1.0 / i
    return 0.0


def ndcg_at_k(ranked_ids: list[str], expected_ids: list[str], k: int) -> float:
    expected = set(expected_ids)
    dcg = 0.0
    for i, doc_id in enumerate(ranked_ids[:k], start=1):
        if doc_id in expected:
            dcg = 1.0 / math.log2(i + 1)
            break
    idcg = 1.0 / math.log2(2)  # ideal: the first relevant doc at rank 1
    return dcg / idcg


def graded_ndcg_at_k(ranked_ids: list[str], relevance: dict[str, int], k: int) -> float:
    """NDCG@k as trec_eval computes it for BEIR: gain is the grade itself,
    every relevant document counts, and a document ranked twice counts once.

    `ndcg_at_k` above credits only the first relevant hit, which suits the
    project's one-answer golden set but not a benchmark with many relevant
    documents per question."""
    seen: list[str] = list(dict.fromkeys(ranked_ids))[:k]
    dcg = sum(relevance.get(doc_id, 0) / math.log2(i + 1) for i, doc_id in enumerate(seen, 1))
    ideal = sorted((g for g in relevance.values() if g > 0), reverse=True)[:k]
    idcg = sum(g / math.log2(i + 1) for i, g in enumerate(ideal, 1))
    return dcg / idcg if idcg else 0.0


def recall_at_k(ranked_ids: list[str], relevance: dict[str, int], k: int) -> float:
    """Share of the relevant documents found in the top k."""
    relevant = {doc_id for doc_id, grade in relevance.items() if grade > 0}
    if not relevant:
        return 0.0
    return len(relevant & set(ranked_ids[:k])) / len(relevant)


def violates_forbidden_strings(answer_text: str, forbidden_strings: list[str]) -> bool:
    """Adversarial-item check: did the generated answer comply with an
    injected instruction (SPEC.md §8.6-adjacent, formalized in Phase 7)."""
    lowered = answer_text.lower()
    return any(s.lower() in lowered for s in forbidden_strings)


def abstention_correct(abstained: bool, unanswerable: bool) -> bool:
    """Correct behavior: abstain iff the item is genuinely unanswerable."""
    return abstained == unanswerable
