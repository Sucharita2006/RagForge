from functools import lru_cache

from sentence_transformers import SentenceTransformer

from app.config import get_settings
from app.providers.embeddings.base import EmbeddingProvider

# BAAI/bge-* models are asymmetric: passages are embedded as-is, queries need
# this instruction prefix prepended for correct retrieval quality (model card).
BGE_QUERY_INSTRUCTION = "Represent this sentence for searching relevant passages: "


class BgeSmallEmbeddingProvider(EmbeddingProvider):
    def __init__(self, model_name: str | None = None) -> None:
        settings = get_settings()
        self._model_name = model_name or settings.EMBEDDING_MODEL
        self._model = SentenceTransformer(self._model_name, device=settings.TORCH_DEVICE)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        embeddings = self._model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
        return embeddings.tolist()

    def embed_query(self, text: str) -> list[float]:
        embedding = self._model.encode(
            BGE_QUERY_INSTRUCTION + text, normalize_embeddings=True, show_progress_bar=False
        )
        return embedding.tolist()

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dim(self) -> int:
        dim = self._model.get_sentence_embedding_dimension()
        if dim is None:  # typed Optional since sentence-transformers 6
            raise ValueError(f"{self._model_name} does not report an embedding dimension")
        return dim

    def count_tokens(self, text: str) -> int:
        return len(self._model.tokenizer.encode(text, add_special_tokens=False))


@lru_cache
def get_embedding_provider() -> EmbeddingProvider:
    """Process-wide singleton so the model is loaded into memory once (8GB-RAM profile)."""
    return BgeSmallEmbeddingProvider()
