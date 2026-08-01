import time

import httpx

from app.config import get_settings
from app.providers.budget_guard import BudgetGuard
from app.providers.llm.base import LLMProvider, LLMResult

_API_BASE = "https://generativelanguage.googleapis.com/v1beta"


class GeminiProvider(LLMProvider):
    """Free-tier Google AI Studio key, used ONLY for judge/testset-gen/
    contextual enrichment (DECISIONS.md 2026-07-30) — never for in-app query
    generation, which stays on the self-hosted Ollama model. Talks to the
    REST API directly via httpx rather than adding the google-genai SDK as a
    dependency for three offline call-sites."""

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

    async def generate(self, system: str, user: str) -> LLMResult:
        await self._budget_guard.check_and_record_call("gemini")

        start = time.monotonic()
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{_API_BASE}/models/{self._model}:generateContent",
                params={"key": self._api_key},
                json={
                    "system_instruction": {"parts": [{"text": system}]},
                    "contents": [{"parts": [{"text": user}]}],
                },
            )
            resp.raise_for_status()
            data = resp.json()
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
