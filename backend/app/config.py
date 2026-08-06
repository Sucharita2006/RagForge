from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- App ---
    APP_NAME: str = "ragforge"
    ENV: str = "local"  # local | ci | production
    API_KEY: str = "dev-demo-key"

    # --- Datastores ---
    DATABASE_URL: str = "postgresql+asyncpg://ragforge:ragforge@postgres:5432/ragforge"
    REDIS_URL: str = "redis://redis:6379/0"

    # --- LLM providers (DECISIONS.md 2026-07-30: self-hosted-first) ---
    LLM_PROVIDER: str = "ollama"  # ollama | gemini
    OLLAMA_BASE_URL: str = "http://host.docker.internal:11434"
    GEN_MODEL: str = "qwen3:4b-instruct"
    GEN_TEMPERATURE: float = 0.1
    MAX_OUTPUT_TOKENS: int = 1024
    # Ollama defaults to a 4096-token context window regardless of what the
    # model actually supports; must cover MAX_CONTEXT_TOKENS + system prompt/
    # JSON-schema overhead + MAX_OUTPUT_TOKENS or generation 400s.
    OLLAMA_NUM_CTX: int = 8192
    # CPU inference of a large context is slow (implementation-plan.md §2.E4
    # profile tradeoff) — generous timeout rather than a false-negative ReadTimeout.
    GEN_TIMEOUT_SECONDS: float = 600.0

    # Optional free-tier hybrid path: judge / testset-gen / enrichment only (DECISIONS.md)
    GOOGLE_API_KEY: str | None = None
    JUDGE_PROVIDER: str = "ollama"  # ollama | gemini
    JUDGE_MODEL: str = "gemini-pro-latest"
    GEMINI_FLASH_MODEL: str = "gemini-flash-latest"
    """Lighter-weight Gemini tier for enrichment/testset-gen (vs. JUDGE_MODEL's Pro tier)."""

    # Alternative free-tier eval-run generation provider (DECISIONS.md 2026-08-06):
    # Gemini's free tier caps at 20 req/day *per model* for a fresh project - too
    # low for a ~39-item full-pipeline eval run. OpenRouter's fresh-account free
    # tier is 20 req/min + 50 req/day, enough for one run. Never used for
    # production /query.
    OPENROUTER_API_KEY: str | None = None
    OPENROUTER_MODEL: str = "inclusionai/ling-3.0-flash:free"

    # --- Embeddings / reranker (DECISIONS.md 2026-07-30: 8GB CPU profile) ---
    EMBEDDING_PROVIDER: str = "bge_small"  # bge_small | bge_m3 | gemini
    EMBEDDING_MODEL: str = "BAAI/bge-small-en-v1.5"
    EMBEDDING_DIM: int = 384
    RERANKER_PROVIDER: str = "minilm"  # minilm | bge_v2_m3 | cohere
    RERANKER_MODEL: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    # the `minicheck` package's own short alias (NOT a HF repo id) - it
    # internally resolves this to lytang/MiniCheck-RoBERTa-Large.
    MINICHECK_MODEL: str = "roberta-large"

    # --- Ingestion / chunking (SPEC.md §7.1) ---
    UPLOAD_DIR: str = "/app/data/uploads"
    # Docling's OCR fallback (RapidOCR) has no internal timeout and can run
    # effectively unbounded on an image-heavy scanned PDF on CPU — falls
    # back to pypdf if exceeded, same as any other Docling failure.
    DOCLING_TIMEOUT_SECONDS: float = 300.0
    CHUNK_SIZE: int = 512
    CHUNK_OVERLAP: int = 64
    PARENT_CHUNK_SIZE: int = 2048
    CONTEXTUAL_ENRICHMENT: bool = True

    # --- Retrieval (SPEC.md §7.1) ---
    DENSE_TOP_K: int = 50
    SPARSE_TOP_K: int = 50
    RRF_K: int = 60
    RERANK_CANDIDATES: int = 50
    FINAL_TOP_K: int = 8
    MAX_CONTEXT_TOKENS: int = 6000
    HYDE: bool = False
    MULTI_QUERY_N: int = 0

    # --- pgvector / query-layer latency architecture (implementation-plan.md §2.E, §3.1) ---
    HNSW_M: int = 16
    HNSW_EF_CONSTRUCTION: int = 200
    HNSW_EF_SEARCH: int = 80
    # off | strict_order | relaxed_order — neutralizes pgvector's documented
    # post-filter under-return bug for the document_id filter (Phase 2).
    HNSW_ITERATIVE_SCAN: str = "relaxed_order"
    HNSW_MAX_SCAN_TUPLES: int = 20000
    # Phase 1 baseline-v0 measured plain float32 `vector`; Phase 2 migrates to
    # `halfvec` (0004_halfvec_migration.py) as a measured before/after.
    EMBEDDING_STORAGE: str = "halfvec"  # vector | halfvec

    # --- Semantic cache ---
    SEMANTIC_CACHE_THRESHOLD: float = 0.92
    SEMANTIC_CACHE_TTL_SECONDS: int = 24 * 3600

    # --- Trust layer (SPEC.md §7.1) ---
    MINICHECK_SUPPORT_THRESHOLD: float = 0.5
    CONFIDENCE_WEIGHT_CLAIM_SUPPORT: float = 0.5
    CONFIDENCE_WEIGHT_RETRIEVAL: float = 0.3
    CONFIDENCE_WEIGHT_SUFFICIENCY: float = 0.2
    ABSTAIN_THRESHOLD: float = 0.55

    # --- Observability (SPEC.md §3.8) ---
    OTEL_EXPORTER: str = "postgres"  # postgres | none
    SPAN_EXPORT_ENABLED: bool = True
    """Kill switch for span persistence - unit tests and CI run with this off
    so a test process never opens a second (sync) DB engine."""
    ONLINE_MONITOR_SAMPLE_SIZE: int = 20
    """Answers sampled per online-monitor run for judge-scored faithfulness."""
    ONLINE_MONITOR_DROP_ALERT_POINTS: float = 5.0
    """Log an alert if 7-day mean faithfulness falls this many points vs the prior window."""

    # Per-1M-token prices (USD) for cost attribution on LLM/embedding spans.
    # Self-hosted models are genuinely $0 marginal cost (local CPU), so the
    # cost column is only meaningful for the hosted providers - kept explicit
    # rather than implied, so a $0 total reads as "self-hosted", not "unmeasured".
    COST_PER_1M_INPUT_TOKENS: dict[str, float] = {
        "ollama": 0.0,
        "bge_small": 0.0,
        "gemini-flash-latest": 0.30,
        "gemini-pro-latest": 1.25,
        "openrouter": 0.0,  # `:free` tier models
    }
    COST_PER_1M_OUTPUT_TOKENS: dict[str, float] = {
        "ollama": 0.0,
        "bge_small": 0.0,
        "gemini-flash-latest": 2.50,
        "gemini-pro-latest": 10.00,
        "openrouter": 0.0,
    }

    # --- Learning flywheel (SPEC.md §3.5) ---
    FINETUNE_TORCH_THREADS: int = 6
    """CPU threads for fine-tuning. Measured on this hardware (2026-08-06):
    batch 32 is the throughput sweet spot at ~30 pairs/s and ~1.5GB peak RSS;
    batch 64 doubles memory and gets *slower*, past the efficient working set."""
    FINETUNE_BATCH_SIZE: int = 32

    # --- Budget guard (DECISIONS.md: caps the free-tier hybrid key) ---
    MAX_DAILY_LLM_CALLS: int = 500
    MAX_DAILY_LLM_TOKENS: int = 2_000_000


@lru_cache
def get_settings() -> Settings:
    return Settings()
