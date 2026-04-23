import functools

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables or .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    bot_token: str = Field(..., alias="BOT_TOKEN")
    database_url: str = Field(..., alias="DATABASE_URL")

    google_places_api_key: str = Field("", alias="GOOGLE_PLACES_API_KEY")
    anthropic_api_key: str = Field("", alias="ANTHROPIC_API_KEY")
    anthropic_model: str = Field("claude-haiku-4-5-20251001", alias="ANTHROPIC_MODEL")

    log_level: str = Field("INFO", alias="LOG_LEVEL")
    default_queries_limit: int = Field(5, alias="DEFAULT_QUERIES_LIMIT")
    max_results_per_query: int = Field(50, alias="MAX_RESULTS_PER_QUERY")
    max_enrich_leads: int = Field(50, alias="MAX_ENRICH_LEADS")
    enrich_concurrency: int = Field(5, alias="ENRICH_CONCURRENCY")
    http_retries: int = Field(3, alias="HTTP_RETRIES")
    http_retry_base_delay: float = Field(0.7, alias="HTTP_RETRY_BASE_DELAY")

    @property
    def sqlalchemy_url(self) -> str:
        """Normalize Railway-style postgres:// URLs to the async driver."""
        url = self.database_url
        if url.startswith("postgres://"):
            url = "postgresql+asyncpg://" + url[len("postgres://") :]
        elif url.startswith("postgresql://") and "+asyncpg" not in url:
            url = "postgresql+asyncpg://" + url[len("postgresql://") :]
        return url


@functools.lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached Settings singleton.

    Deferred until first call so that pydantic validation (and any
    missing-env-var errors) happens after logging is configured, making
    failures visible in Railway logs instead of causing a silent crash
    at import time.
    """
    return Settings()  # type: ignore[call-arg]
