"""Daily LLM call/token cap (implementation-plan.md amendment C1).

Applies uniformly to every provider (not just the paid free-tier Gemini key)
as a cheap safety net against runaway loops; the Gemini key is the one it's
actually meant to protect, starting when Phase 2 (enrichment) and Phase 3
(judge) begin using it.
"""

from datetime import date, timedelta

import redis.asyncio as redis

from app.config import get_settings

_TTL_SECONDS = int(timedelta(days=2).total_seconds())


class BudgetExceededError(Exception):
    pass


class BudgetGuard:
    def __init__(self) -> None:
        settings = get_settings()
        self._redis = redis.from_url(settings.REDIS_URL)
        self._max_calls = settings.MAX_DAILY_LLM_CALLS
        self._max_tokens = settings.MAX_DAILY_LLM_TOKENS

    def _key(self, provider: str, metric: str) -> str:
        return f"budget:{provider}:{metric}:{date.today().isoformat()}"

    async def check_and_record_call(self, provider: str) -> None:
        key = self._key(provider, "calls")
        calls = await self._redis.incr(key)
        if calls == 1:
            await self._redis.expire(key, _TTL_SECONDS)
        if calls > self._max_calls:
            raise BudgetExceededError(f"{provider}: daily call cap ({self._max_calls}) exceeded")

    async def record_tokens(self, provider: str, tokens: int) -> None:
        if tokens <= 0:
            return
        key = self._key(provider, "tokens")
        total = await self._redis.incrby(key, tokens)
        if total == tokens:
            await self._redis.expire(key, _TTL_SECONDS)
        # Tokens are only known after the call completes, so this is reported,
        # not pre-blocked; it still surfaces before the *next* call is allowed
        # through if the app checks get_usage() (e.g. a Settings page later).
