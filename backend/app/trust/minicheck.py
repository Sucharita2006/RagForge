from functools import lru_cache

from app.config import get_settings


class MiniCheckProvider:
    """Per-sentence NLI-style claim verification against source spans
    (SPEC.md §3.3). The `minicheck` package's RoBERTa-Large checkpoint is
    ~1.4GB (implementation-plan.md §3: 8GB CPU profile) - loaded lazily via
    get_minicheck_provider() so it only enters memory once a query actually
    needs claim verification, not at worker/API startup.
    """

    def __init__(self, model_name: str | None = None) -> None:
        settings = get_settings()
        from minicheck.minicheck import MiniCheck  # heavy import, deferred to first use

        self._model_name = model_name or settings.MINICHECK_MODEL
        self._scorer = MiniCheck(model_name=self._model_name)

    def score(self, claims: list[str], docs: list[str]) -> list[float]:
        """Support probability per (doc, claim) pair, same order/length as
        input. MiniCheck is a sentence-level checker (one claim at a time,
        not a whole multi-sentence answer) - callers are expected to have
        already split the answer into individual claim sentences."""
        if not claims:
            return []
        _, raw_probs, _, _ = self._scorer.score(docs=docs, claims=claims)
        return [float(p) for p in raw_probs]

    @property
    def model_name(self) -> str:
        return self._model_name


@lru_cache
def get_minicheck_provider() -> MiniCheckProvider:
    """Process-wide singleton so the model is loaded into memory once (8GB-RAM profile)."""
    return MiniCheckProvider()
