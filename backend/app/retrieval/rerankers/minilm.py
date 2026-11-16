from functools import lru_cache

from sentence_transformers import CrossEncoder

from app.config import get_settings
from app.retrieval.rerankers.base import RerankerProvider


class MiniLMReranker(RerankerProvider):
    def __init__(self, model_name: str | None = None) -> None:
        settings = get_settings()
        self._model_name = model_name or settings.RERANKER_MODEL
        self._model = CrossEncoder(
            self._model_name,
            device=settings.TORCH_DEVICE,
            max_length=settings.RERANKER_MAX_LENGTH,
        )

    def rerank(self, query: str, documents: list[str]) -> list[float]:
        pairs = [(query, doc) for doc in documents]
        scores = self._model.predict(pairs)
        return [float(s) for s in scores]

    @property
    def model_name(self) -> str:
        return self._model_name


@lru_cache
def get_reranker_provider(model_name: str | None = None) -> RerankerProvider:
    """Process-wide singleton *per model path*, so each distinct model is
    loaded into memory once (8GB-RAM profile).

    Keyed by `model_name` so promoting a fine-tuned reranker (Phase 6) swaps
    the loaded model without a redeploy, while still never re-loading the
    same weights twice. `None` keeps the config default for callers that
    don't resolve through the registry (e.g. the CI fixture gate).
    """
    return MiniLMReranker(model_name)
