from pydantic import BaseModel


class GoldenItem(BaseModel):
    """One row of `eval-datasets/<version>/*.jsonl` (SPEC.md §8.3)."""

    id: str
    type: str
    """single_hop | multi_hop | unanswerable | adversarial"""
    question: str
    reference_answer: str | None = None
    expected_arxiv_ids: list[str] = []
    unanswerable: bool = False
    forbidden_strings: list[str] = []
    relevance: dict[str, int] = {}
    """Graded judgments (document external id -> grade) for public benchmark
    sets such as BEIR, whose questions have several relevant documents.
    When present the runner also reports graded NDCG@10 and recall@10."""
