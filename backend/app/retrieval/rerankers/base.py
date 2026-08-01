from abc import ABC, abstractmethod


class RerankerProvider(ABC):
    @abstractmethod
    def rerank(self, query: str, documents: list[str]) -> list[float]:
        """Return a relevance score per document, in the same order as input."""

    @property
    @abstractmethod
    def model_name(self) -> str: ...
