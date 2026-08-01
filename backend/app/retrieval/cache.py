import json
import math
import uuid

import redis.asyncio as redis

from app.config import get_settings

settings = get_settings()

_CACHE_INDEX_KEY = "semantic_cache:index"
_CORPUS_VERSION_KEY = "corpus_version"


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


async def get_corpus_version(redis_client: redis.Redis | None = None) -> str:
    """Monotonic counter bumped once per successful ingestion — used to
    invalidate semantic-cache entries when the corpus changes (SPEC.md §3.2
    step 2)."""
    r = redis_client or redis.from_url(settings.REDIS_URL)
    version = await r.get(_CORPUS_VERSION_KEY)
    if version is None:
        return "0"
    return version.decode() if isinstance(version, bytes) else version


async def bump_corpus_version(redis_client: redis.Redis | None = None) -> None:
    r = redis_client or redis.from_url(settings.REDIS_URL)
    await r.incr(_CORPUS_VERSION_KEY)


class SemanticCache:
    """Redis-backed semantic cache (SPEC.md §3.2 step 2): embed the query, and
    if a cached (query, answer, corpus_version) entry scores >= threshold on
    cosine similarity, return it instead of re-running retrieval+generation.

    Brute-force cosine over cached entries in Python — no vector-search
    Redis module assumed. Fine at portfolio-demo cache sizes (dozens to a
    few hundred entries); not meant to scale to production query volume.
    """

    def __init__(self) -> None:
        self._redis = redis.from_url(settings.REDIS_URL)

    async def get(self, query_embedding: list[float], corpus_version: str) -> dict | None:
        entry_keys = await self._redis.smembers(_CACHE_INDEX_KEY)
        best_score = 0.0
        best_entry: dict | None = None
        for key in entry_keys:
            raw = await self._redis.get(key)
            if raw is None:
                await self._redis.srem(_CACHE_INDEX_KEY, key)
                continue
            entry = json.loads(raw)
            if entry.get("corpus_version") != corpus_version:
                continue
            score = _cosine_similarity(query_embedding, entry["embedding"])
            if score > best_score:
                best_score = score
                best_entry = entry
        if best_entry is not None and best_score >= settings.SEMANTIC_CACHE_THRESHOLD:
            return best_entry["response"]
        return None

    async def set(self, query_embedding: list[float], response: dict, corpus_version: str) -> None:
        key = f"semantic_cache:entry:{uuid.uuid4()}"
        payload = json.dumps(
            {"embedding": query_embedding, "response": response, "corpus_version": corpus_version}
        )
        await self._redis.set(key, payload, ex=settings.SEMANTIC_CACHE_TTL_SECONDS)
        await self._redis.sadd(_CACHE_INDEX_KEY, key)
        await self._redis.expire(_CACHE_INDEX_KEY, settings.SEMANTIC_CACHE_TTL_SECONDS)
