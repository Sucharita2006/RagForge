from pydantic import BaseModel, Field


class VerifiedClaim(BaseModel):
    """SPEC.md §5 `answers.claims` entry, extended with MiniCheck's verdict."""

    text: str
    citations: list[str]
    support_prob: float | None = Field(
        default=None, description="MiniCheck entailment probability, None if never scored."
    )
    verdict: str = Field(description="'supported' | 'unsupported' | 'unscored'")
