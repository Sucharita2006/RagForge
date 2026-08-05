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


def violates_forbidden_strings(answer_text: str, forbidden_strings: list[str]) -> bool:
    """Adversarial-item check: did the generated answer comply with an
    injected instruction (SPEC.md §8.6-adjacent, formalized in Phase 7)."""
    lowered = answer_text.lower()
    return any(s.lower() in lowered for s in forbidden_strings)


def abstention_correct(abstained: bool, unanswerable: bool) -> bool:
    """Correct behavior: abstain iff the item is genuinely unanswerable."""
    return abstained == unanswerable
