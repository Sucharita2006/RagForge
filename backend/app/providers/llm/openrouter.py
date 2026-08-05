import asyncio
import time

import httpx

from app.config import get_settings
from app.providers.budget_guard import BudgetGuard
from app.providers.llm.base import LLMProvider, LLMResult

_API_BASE = "https://openrouter.ai/api/v1"
_RETRY_STATUS_CODES = {429, 503}
_MAX_RETRIES = 4
_BACKOFF_BASE_SECONDS = 5.0


class OpenRouterProvider(LLMProvider):
    """Free-tier OpenRouter key, OpenAI-compatible chat completions API.
    Alternative eval-run generation provider (DECISIONS.md 2026-08-06) for
    when Gemini's free tier (20 req/day per model, for a fresh project) is
    too low for a full eval-pipeline run - OpenRouter's fresh-account free
    tier is 20 req/min + 50 req/day, no billing history needed. Never used
    for production /query, which stays on the self-hosted Ollama model."""

    def __init__(self, model: str | None = None) -> None:
        settings = get_settings()
        if not settings.OPENROUTER_API_KEY:
            raise RuntimeError("OpenRouterProvider requires OPENROUTER_API_KEY to be set")
        self._api_key = settings.OPENROUTER_API_KEY
        self._model = model or settings.OPENROUTER_MODEL
        self._budget_guard = BudgetGuard()

    @property
    def model_name(self) -> str:
        return self._model

    async def _post_with_retry(self, client: httpx.AsyncClient, system: str, user: str) -> dict:
        """Same free-tier-quota reality as GeminiProvider (DECISIONS.md
        2026-08-04): retry 429/503 with exponential backoff (or the
        server's Retry-After header) rather than surfacing the first
        transient failure as a hard error."""
        for attempt in range(_MAX_RETRIES + 1):
            resp = await client.post(
                "/chat/completions",
                json={
                    "model": self._model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                },
            )
            if resp.status_code not in _RETRY_STATUS_CODES or attempt == _MAX_RETRIES:
                resp.raise_for_status()
                return dict(resp.json())
            retry_after = resp.headers.get("retry-after")
            delay = float(retry_after) if retry_after else _BACKOFF_BASE_SECONDS * (2**attempt)
            await asyncio.sleep(delay)
        raise AssertionError("unreachable")  # loop always returns or raises above

    async def generate(self, system: str, user: str) -> LLMResult:
        await self._budget_guard.check_and_record_call("openrouter")

        start = time.monotonic()
        async with httpx.AsyncClient(
            base_url=_API_BASE,
            headers={"Authorization": f"Bearer {self._api_key}"},
            timeout=60.0,
        ) as client:
            data = await self._post_with_retry(client, system, user)
        latency_ms = int((time.monotonic() - start) * 1000)

        text = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        input_tokens = usage.get("prompt_tokens")
        output_tokens = usage.get("completion_tokens")
        await self._budget_guard.record_tokens(
            "openrouter", (input_tokens or 0) + (output_tokens or 0)
        )

        return LLMResult(
            text=text,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
        )
