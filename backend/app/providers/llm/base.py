from abc import ABC, abstractmethod
from typing import TypedDict


class LLMResult(TypedDict):
    text: str
    input_tokens: int | None
    output_tokens: int | None
    latency_ms: int


class LLMProvider(ABC):
    @abstractmethod
    async def generate(self, system: str, user: str) -> LLMResult:
        """Generate a plain-text response, alongside token/latency accounting
        for the answers table.

        DECISIONS.md 2026-07-31: no JSON-schema `format` constraint — under
        grammar-constrained decoding our 4B local model reliably took the
        trivial empty-answer shortcut instead of real cited content; plain
        prose + parsed citation markers (app/generation/parser.py) is both
        faster and more reliable.
        """

    @property
    @abstractmethod
    def model_name(self) -> str: ...
