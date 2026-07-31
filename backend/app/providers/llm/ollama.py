import time

import httpx

from app.config import get_settings
from app.providers.budget_guard import BudgetGuard
from app.providers.llm.base import LLMProvider, LLMResult


class OllamaProvider(LLMProvider):
    def __init__(self) -> None:
        settings = get_settings()
        self._base_url = settings.OLLAMA_BASE_URL
        self._model = settings.GEN_MODEL
        self._temperature = settings.GEN_TEMPERATURE
        self._max_tokens = settings.MAX_OUTPUT_TOKENS
        self._num_ctx = settings.OLLAMA_NUM_CTX
        self._timeout = settings.GEN_TIMEOUT_SECONDS
        self._budget_guard = BudgetGuard()

    @property
    def model_name(self) -> str:
        return self._model

    async def generate(self, system: str, user: str) -> LLMResult:
        await self._budget_guard.check_and_record_call("ollama")

        start = time.monotonic()
        async with httpx.AsyncClient(base_url=self._base_url, timeout=self._timeout) as client:
            resp = await client.post(
                "/api/chat",
                json={
                    "model": self._model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    "stream": False,
                    "options": {
                        "temperature": self._temperature,
                        "num_predict": self._max_tokens,
                        "num_ctx": self._num_ctx,
                    },
                },
            )
            resp.raise_for_status()
            data = resp.json()

        latency_ms = int((time.monotonic() - start) * 1000)
        output_tokens = data.get("eval_count")
        await self._budget_guard.record_tokens(
            "ollama", (data.get("prompt_eval_count") or 0) + (output_tokens or 0)
        )

        return LLMResult(
            text=data["message"]["content"],
            input_tokens=data.get("prompt_eval_count"),
            output_tokens=output_tokens,
            latency_ms=latency_ms,
        )
