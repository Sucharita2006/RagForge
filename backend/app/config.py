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
    JUDGE_MODEL: str = "gemini-2.5-pro"

    # --- Embeddings / reranker (DECISIONS.md 2026-07-30: 8GB CPU profile) ---
    EMBEDDING_PROVIDER: str = "bge_small"  # bge_small | bge_m3 | gemini
    EMBEDDING_MODEL: str = "BAAI/bge-small-en-v1.5"
    EMBEDDING_DIM: int = 384
    RERANKER_PROVIDER: str = "minilm"  # minilm | bge_v2_m3 | cohere
    RERANKER_MODEL: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    MINICHECK_MODEL: str = "lytang/MiniCheck-RoBERTa-Large"

    # --- Ingestion / chunking (SPEC.md §7.1) ---
    UPLOAD_DIR: str = "/app/data/uploads"
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
    # off | strict_order | relaxed_order — inert until Phase 2 adds filtered queries
    HNSW_ITERATIVE_SCAN: str = "relaxed_order"
    HNSW_MAX_SCAN_TUPLES: int = 20000
    # Phase 1 baseline-v0 uses plain float32 `vector` on purpose, so the Phase 2
    # migration to `halfvec` is a measured before/after, not an unmeasured start.
    EMBEDDING_STORAGE: str = "vector"  # vector | halfvec

    # --- Semantic cache ---
    SEMANTIC_CACHE_THRESHOLD: float = 0.92
    SEMANTIC_CACHE_TTL_SECONDS: int = 24 * 3600

    # --- Trust layer (SPEC.md §7.1) ---
    MINICHECK_SUPPORT_THRESHOLD: float = 0.5
    CONFIDENCE_WEIGHT_CLAIM_SUPPORT: float = 0.5
    CONFIDENCE_WEIGHT_RETRIEVAL: float = 0.3
    CONFIDENCE_WEIGHT_SUFFICIENCY: float = 0.2
    ABSTAIN_THRESHOLD: float = 0.55

    # --- Observability ---
    OTEL_EXPORTER: str = "postgres"

    # --- Budget guard (DECISIONS.md: caps the free-tier hybrid key) ---
    MAX_DAILY_LLM_CALLS: int = 500
    MAX_DAILY_LLM_TOKENS: int = 2_000_000


@lru_cache
def get_settings() -> Settings:
    return Settings()
