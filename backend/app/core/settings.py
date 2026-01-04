from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="LAB_TUTOR_",
        extra="ignore",
    )

    app_name: str = "Lab Tutor Backend"
    secret_key: str = Field(
        "change-this-secret",
        description="JWT signing secret. Override in production via LAB_TUTOR_SECRET_KEY.",
    )
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 15  # Short-lived access token
    refresh_token_expire_days: int = 7  # Long-lived refresh token
    database_url: str = Field(
        default="sqlite:///./data/app.db",
        description="SQLAlchemy database URL",
    )
    azure_storage_connection_string: str | None = Field(
        default=None, description="Azure Blob Storage Connection String"
    )
    azure_container_name: str = Field(
        default="class-presentations", description="Container name for presentations"
    )

    # Neo4j (Knowledge Graph)
    neo4j_uri: str | None = Field(default=None, description="Neo4j URI")
    neo4j_username: str | None = Field(default=None, description="Neo4j username")
    neo4j_password: str | None = Field(default=None, description="Neo4j password")
    neo4j_database: str = Field(default="neo4j", description="Neo4j database name")

    # LLM (OpenAI-compatible; supports proxies like XiaoCase)
    llm_api_key: str | None = Field(
        default=None,
        description="LLM API key (OpenAI-compatible). Preferred: LAB_TUTOR_LLM_API_KEY.",
        validation_alias=AliasChoices(
            # Preferred (handled automatically via env_prefix + field name):
            # - LAB_TUTOR_LLM_API_KEY
            # Back-compat:
            "XIAO_CASE_API_KEY",
            "XIAOCASE_API_KEY",
            # Common OpenAI-style env var name:
            "OPENAI_API_KEY",
        ),
    )
    llm_base_url: str = Field(
        default="https://api.xiaocaseai.com/v1",
        description="OpenAI-compatible base URL. Preferred: LAB_TUTOR_LLM_BASE_URL.",
        validation_alias=AliasChoices(
            # Preferred (handled automatically via env_prefix + field name):
            # - LAB_TUTOR_LLM_BASE_URL
            # Back-compat:
            "XIAO_CASE_API_BASE",
            "XIAOCASE_API_BASE",
            # Common OpenAI-style env var name:
            "OPENAI_BASE_URL",
        ),
    )
    llm_model: str = Field(
        default="deepseek-v3.2",
        description="Model name/id. Preferred: LAB_TUTOR_LLM_MODEL.",
        validation_alias=AliasChoices(
            # Preferred (handled automatically via env_prefix + field name):
            # - LAB_TUTOR_LLM_MODEL
            # Back-compat:
            "XIAO_CASE_MODEL",
            "XIAOCASE_MODEL",
            # Common pattern in some deployments:
            "OPENAI_MODEL",
        ),
    )
    llm_timeout_seconds: int = Field(
        default=600,
        description="LLM request timeout in seconds",
    )
    llm_max_completion_tokens: int = Field(
        default=4096,
        description="Max completion tokens for extraction responses",
    )

    extraction_workers: int = Field(
        default=4,
        description=(
            "Max worker threads for course file extraction. "
            "Embeddings orchestration uses the same worker count."
        ),
    )

    # Embeddings (OpenAI-compatible; defaults to the same creds as LLM)
    embedding_model: str = Field(
        default="text-embedding-3-small",
        description="Embedding model name/id. Override via LAB_TUTOR_EMBEDDING_MODEL.",
    )
    embedding_dims: int | None = Field(
        default=1536,
        description=(
            "Embedding vector dimensions. Used for validation + Neo4j vector indexes. "
            "Set to null/empty to disable dim enforcement and vector index creation."
        ),
    )
    embedding_api_key: str | None = Field(
        default=None,
        description=(
            "Embedding API key (OpenAI-compatible). Defaults to LAB_TUTOR_LLM_API_KEY if unset."
        ),
    )
    embedding_base_url: str | None = Field(
        default=None,
        description=(
            "Embedding base URL (OpenAI-compatible). Defaults to LAB_TUTOR_LLM_BASE_URL if unset."
        ),
    )
    embedding_batch_size: int = Field(
        default=64,
        description="Max texts per embeddings request batch.",
    )
    embedding_timeout_seconds: int = Field(
        default=120,
        description="Embeddings request timeout in seconds.",
    )
    embedding_stale_seconds: int = Field(
        default=3600,
        description=(
            "If course embeddings are IN_PROGRESS longer than this, the status endpoint will "
            "auto-restart embeddings in the background."
        ),
    )
    embedding_max_retries: int = Field(
        default=3,
        description="Max retries per embeddings batch.",
    )
    embedding_retry_base_seconds: float = Field(
        default=1.0,
        description="Base seconds for exponential backoff between embedding retries.",
    )

    # LangSmith (observability / tracing)
    langsmith_api_key: str | None = Field(
        default=None,
        description="LangSmith API key. Preferred: LAB_TUTOR_LANGSMITH_API_KEY.",
        validation_alias=AliasChoices(
            # Preferred (handled automatically via env_prefix + field name):
            # - LAB_TUTOR_LANGSMITH_API_KEY
            # Fallbacks (useful outside docker-compose):
            "LANGSMITH_API_KEY",
            "LANGCHAIN_API_KEY",
        ),
    )
    langsmith_project: str = Field(
        default="lab-tutor-backend",
        description="LangSmith project name. Preferred: LAB_TUTOR_LANGSMITH_PROJECT.",
        validation_alias=AliasChoices(
            # Preferred (handled automatically via env_prefix + field name):
            # - LAB_TUTOR_LANGSMITH_PROJECT
            # Fallbacks (useful outside docker-compose):
            "LANGSMITH_PROJECT",
            "LANGCHAIN_PROJECT",
        ),
    )

    # CORS
    # Comma-separated list of allowed origins for browser clients (no wildcards).
    # Example:
    #   LAB_TUTOR_CORS_ALLOW_ORIGINS="https://gray-meadow-055f6ba1e.1.azurestaticapps.net,https://yourdomain.com"
    cors_allow_origins: str = Field(
        default=(
            "http://localhost:5173,http://127.0.0.1:5173,"
            "http://localhost:5174,http://127.0.0.1:5174,"
            "http://localhost:3000,http://127.0.0.1:3000"
        ),
        description="Comma-separated CORS allowlist origins.",
    )
    cors_allow_credentials: bool = Field(
        default=False,
        description="Whether to allow credentials in CORS. Prefer false when using Bearer tokens.",
    )

    # Observability
    request_timing_header_enabled: bool = Field(
        default=True,
        description=(
            "Whether to add X-Request-Id and X-Request-Duration-Ms response headers."
        ),
    )
    request_timing_log_enabled: bool = Field(
        default=False,
        description=(
            "Whether to log per-request timing. When enabled, slow requests are logged at INFO, others at DEBUG."
        ),
    )
    slow_request_ms: int = Field(
        default=500,
        description="Threshold (ms) for considering a request slow when logging timings.",
    )


settings = Settings()
