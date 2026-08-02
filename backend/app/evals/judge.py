import hashlib
import json
import re

import redis.asyncio as redis

from app.config import get_settings
from app.providers.llm.base import LLMProvider

settings = get_settings()

JUDGE_PROMPT_VERSION = "v1"
_CACHE_PREFIX = "judge_cache"
_CACHE_TTL_SECONDS = 30 * 24 * 3600

# One combined pointwise-rubric call per answerable item instead of four
# separate ones (SPEC.md §8.4) - implementation-plan.md C2 caches by
# (question_id, answer_hash, judge_model, prompt_version) so a rerun only
# pays for genuinely new answers, but the bigger lever on this hardware is
# not paying for four LLM round trips when one well-structured prompt gets
# all four scores in a single response (same plain-text-over-JSON-schema
# lesson as DECISIONS.md 2026-07-31's generation-prompt finding).
JUDGE_PROMPT = """You are a strict evaluator scoring a RAG system's output.

Question: {question}

Retrieved context:
---
{context}
---

Generated answer:
---
{answer}
---

Reference answer (ground truth, for correctness comparison only):
---
{reference_answer}
---

Score each of the following from 0.0 to 1.0:
- FAITHFULNESS: does every claim in the generated answer follow from the
  retrieved context (no unsupported/hallucinated claims)? 1.0 = fully
  grounded, 0.0 = entirely unsupported.
- ANSWER_CORRECTNESS: does the generated answer convey the same
  information as the reference answer? 1.0 = fully correct/equivalent,
  0.0 = wrong or contradictory.
- CONTEXT_PRECISION: what fraction of the retrieved context is actually
  relevant to answering the question? 1.0 = all relevant, 0.0 = none
  relevant.
- CONTEXT_RECALL: does the retrieved context contain everything needed to
  produce the reference answer? 1.0 = fully sufficient, 0.0 = missing key
  information.

Respond in exactly this format, nothing else:
FAITHFULNESS: <score>
ANSWER_CORRECTNESS: <score>
CONTEXT_PRECISION: <score>
CONTEXT_RECALL: <score>
RATIONALE: <one or two sentence justification>"""

_SCORE_FIELDS = ("faithfulness", "answer_correctness", "context_precision", "context_recall")


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def _answer_hash(answer_text: str) -> str:
    return hashlib.sha256(answer_text.encode()).hexdigest()[:16]


def _cache_key(question_id: str, answer_hash: str, judge_model: str) -> str:
    return f"{_CACHE_PREFIX}:{question_id}:{answer_hash}:{judge_model}:{JUDGE_PROMPT_VERSION}"


def parse_judge_scores(text_out: str) -> dict:
    scores: dict = {}
    for field in _SCORE_FIELDS:
        match = re.search(rf"{field.upper()}:\s*(-?[0-9.]+)", text_out)
        scores[field] = _clamp01(float(match.group(1))) if match else None
    rationale_match = re.search(r"RATIONALE:\s*(.+)", text_out, re.DOTALL)
    scores["rationale"] = rationale_match.group(1).strip() if rationale_match else None
    return scores


class JudgeProvider:
    """LLM-as-judge (SPEC.md §8.4). Defaults to whatever LLMProvider the
    caller passes in - self-hosted-only for now (DECISIONS.md 2026-08-01),
    a Gemini-backed provider can be swapped in later without touching this
    class, matching the provider-interface pattern from Phase 1/2."""

    def __init__(self, llm: LLMProvider, redis_client: redis.Redis | None = None) -> None:
        self._llm = llm
        self._redis = redis_client or redis.from_url(settings.REDIS_URL)

    async def score(
        self,
        question_id: str,
        question: str,
        context: str,
        answer: str,
        reference_answer: str | None,
    ) -> dict:
        answer_hash = _answer_hash(answer)
        cache_key = _cache_key(question_id, answer_hash, self._llm.model_name)
        cached = await self._redis.get(cache_key)
        if cached is not None:
            scores = json.loads(cached)
            scores["cache_hit"] = True
            scores["judge_model"] = self._llm.model_name
            return scores

        prompt = JUDGE_PROMPT.format(
            question=question,
            context=context[:4000],  # keep the judge prompt bounded on CPU
            answer=answer,
            reference_answer=reference_answer or "(none provided - not applicable)",
        )
        raw = await self._llm.generate("You are a strict, careful RAG evaluator.", prompt)
        scores = parse_judge_scores(raw["text"])
        await self._redis.set(cache_key, json.dumps(scores), ex=_CACHE_TTL_SECONDS)
        scores["cache_hit"] = False
        scores["judge_model"] = self._llm.model_name
        return scores
