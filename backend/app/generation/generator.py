from app.generation.parser import parse_answer
from app.generation.prompts import SYSTEM_PROMPT, build_user_prompt
from app.generation.schemas import GeneratedAnswer
from app.providers.llm.base import LLMProvider, LLMResult


async def generate_answer(
    llm: LLMProvider, question: str, context: str, valid_chunk_ids: set[str]
) -> tuple[GeneratedAnswer, LLMResult]:
    result = await llm.generate(SYSTEM_PROMPT, build_user_prompt(question, context))
    answer = parse_answer(result["text"], valid_chunk_ids)
    return answer, result
