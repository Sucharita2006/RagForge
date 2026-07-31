from pydantic import BaseModel, Field


class ClaimOut(BaseModel):
    text: str = Field(description="One sentence of the answer.")
    citations: list[str] = Field(description="chunk_id values this sentence is grounded in.")


class GeneratedAnswer(BaseModel):
    """SPEC.md §3.3 structured generation output."""

    answer_sentences: list[ClaimOut]
    insufficient_context: bool = Field(
        description="True if the retrieved context lacks enough information to answer."
    )
