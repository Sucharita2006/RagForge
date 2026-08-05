import asyncio
import time

import httpx

from app.config import get_settings
from app.providers.budget_guard import BudgetGuard
from app.providers.llm.base import LLMProvider, LLMResult

_API_BASE = "https://generativelanguage.googleapis.com/v1beta"
_RETRY_STATUS_CODES = {429, 503}
_MAX_RETRIES = 4
_BACKOFF_BASE_SECONDS = 5.0


class GeminiProvider(LLMProvider):
    """Free-tier Google AI Studio key. Used for judge/testset-gen/contextual
    enrichment (DECISIONS.md 2026-07-30), and optionally as an eval run's
    generation provider when local CPU/RAM is the constraint (DECISIONS.md
    2026-08-03) — never for production /query, which stays on the
    self-hosted Ollama model. Talks to the REST API directly via httpx
    rather than adding the google-genai SDK as a dependency for these
    offline call-sites."""

    def __init__(self, model: str | None = None) -> None:
        settings = get_settings()
        if not settings.GOOGLE_API_KEY:
            raise RuntimeError("GeminiProvider requires GOOGLE_API_KEY to be set")
        self._api_key = settings.GOOGLE_API_KEY
        self._model = model or settings.GEMINI_FLASH_MODEL
        self._budget_guard = BudgetGuard()

    @property
    def model_name(self) -> str:
        return self._model

    async def _post_with_retry(self, client: httpx.AsyncClient, system: str, user: str) -> dict:
        """The free tier's per-minute quota is easy to exceed in a batch
        loop (an eval run firing calls back-to-back hit this live, 27/39
        items failing on 429 - DECISIONS.md 2026-08-04) - retry with
        exponential backoff on 429/503 rather than surfacing the first
        transient failure as a hard error."""
        for attempt in range(_MAX_RETRIES + 1):
            resp = await client.post(
                f"{_API_BASE}/models/{self._model}:generateContent",
                params={"key": self._api_key},
                json={
                    "system_instruction": {"parts": [{"text": system}]},
                    "contents": [{"parts": [{"text": user}]}],
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
        await self._budget_guard.check_and_record_call("gemini")

        start = time.monotonic()
        async with httpx.AsyncClient(timeout=60.0) as client:
            data = await self._post_with_retry(client, system, user)
        latency_ms = int((time.monotonic() - start) * 1000)

        text = data["candidates"][0]["content"]["parts"][0]["text"]
        usage = data.get("usageMetadata", {})
        input_tokens = usage.get("promptTokenCount")
        output_tokens = usage.get("candidatesTokenCount")
        await self._budget_guard.record_tokens("gemini", (input_tokens or 0) + (output_tokens or 0))

        return LLMResult(
            text=text,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
        )
