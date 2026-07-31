from abc import ABC, abstractmethod


class EmbeddingProvider(ABC):
    @abstractmethod
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed chunk/document text (no query instruction prefix)."""

    @abstractmethod
    def embed_query(self, text: str) -> list[float]:
        """Embed a user query (asymmetric models prepend a retrieval instruction)."""

    @property
    @abstractmethod
    def model_name(self) -> str: ...

    @property
    @abstractmethod
    def dim(self) -> int: ...

    @abstractmethod
    def count_tokens(self, text: str) -> int:
        """Token count under this model's own tokenizer — used for chunk sizing
        so chunks reliably fit the embedder's context window."""
