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
