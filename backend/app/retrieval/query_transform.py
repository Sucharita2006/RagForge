from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.answers import Answer
from app.models.queries import Query
from app.providers.llm.base import LLMProvider

REWRITE_SYSTEM_PROMPT = (
    "Given a conversation history and a follow-up question, rewrite the "
    "follow-up question to be a standalone question that includes all "
    'necessary context, resolving pronouns ("it", "that", "they") '
    "using the history. If the question is already standalone, return it "
    "unchanged. Respond with ONLY the rewritten question and nothing else — "
    "no preamble, no quotes."
)

_HISTORY_TURNS = 3


async def fetch_recent_history(db: AsyncSession, session_id: str) -> list[tuple[str, str]]:
    """Last few (question, answer) turns for a session, oldest first — used
    to resolve pronouns/context in a follow-up question (SPEC.md §3.2 step 1)."""
    stmt = (
        select(Query, Answer)
        .join(Answer, Answer.query_id == Query.id)
        .where(Query.session_id == session_id)
        .order_by(Query.created_at.desc())
        .limit(_HISTORY_TURNS)
    )
    result = await db.execute(stmt)
    rows = list(result.all())[::-1]  # oldest first
    history = []
    for query_row, answer_row in rows:
        answer_text = " ".join(c["text"] for c in answer_row.claims) or "(no answer)"
        history.append((query_row.raw_text, answer_text))
    return history


def build_rewrite_prompt(history: list[tuple[str, str]], question: str) -> str:
    history_text = "\n".join(f"Q: {q}\nA: {a}" for q, a in history)
    return f"Conversation history:\n{history_text}\n\nFollow-up question: {question}"


async def rewrite_query(llm: LLMProvider, history: list[tuple[str, str]], question: str) -> str:
    """Skips the extra LLM call entirely when there's no history — most
    single-turn demo queries pay zero rewrite latency cost."""
    if not history:
        return question
    result = await llm.generate(REWRITE_SYSTEM_PROMPT, build_rewrite_prompt(history, question))
    rewritten = result["text"].strip().strip('"')
    return rewritten if rewritten else question
