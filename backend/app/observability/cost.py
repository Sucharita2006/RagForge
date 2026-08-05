from app.config import get_settings


def compute_cost_usd(
    model: str | None, input_tokens: int | None, output_tokens: int | None
) -> float:
    """Per-span cost from config's price table (SPEC.md §3.8: "LLM/embedding
    spans record input/output tokens and computed cost (price table in
    config)").

    An unknown model returns 0.0 rather than raising: a missing price entry
    should never break a live query, and every self-hosted model in this
    project is genuinely $0 marginal cost anyway. Callers that need to
    distinguish "free" from "unpriced" should check the model name against
    the table directly.
    """
    if not model:
        return 0.0
    settings = get_settings()
    input_price = settings.COST_PER_1M_INPUT_TOKENS.get(model, 0.0)
    output_price = settings.COST_PER_1M_OUTPUT_TOKENS.get(model, 0.0)
    return (input_tokens or 0) / 1_000_000 * input_price + (
        output_tokens or 0
    ) / 1_000_000 * output_price
