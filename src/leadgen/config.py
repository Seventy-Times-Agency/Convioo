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

    # Optional. When set, background searches are enqueued to Redis via arq
    # instead of running in-process — required for production scale. When
    # unset, the web API falls back to ``asyncio.create_task`` so local dev
    # and small deployments still work.
    redis_url: str = Field("", alias="REDIS_URL")

    # Web API: single shared API key that the frontend sends as
    # ``X-API-Key`` on every request. Simple enough for agency-internal
    # use; real per-user auth (magic link + session cookie) lands once
    # public sign-up is opened.
    web_api_key: str = Field("", alias="WEB_API_KEY")
    # Comma-separated origins Vercel will hit from. Empty → no CORS.
    web_cors_origins: str = Field("", alias="WEB_CORS_ORIGINS")

    # Resend (email-sending) — optional. When empty, send_email() logs
    # the would-be email instead of dispatching, so signup / verification
    # works in dev without external setup.
    resend_api_key: str = Field("", alias="RESEND_API_KEY")
    email_from: str = Field(
        "Convioo <[email protected]>", alias="EMAIL_FROM"
    )
    # Public site URL — verification links are minted relative to this.
    # MUST be set on Railway to the live Vercel domain (or custom domain),
    # otherwise email verification / invite links will point at localhost.
    # Default kept dev-friendly so the local stack works without setup.
    public_app_url: str = Field(
        "http://localhost:3000", alias="PUBLIC_APP_URL"
    )

    # JWT signing for the new email + password sessions.
    auth_jwt_secret: str = Field("", alias="AUTH_JWT_SECRET")
    auth_session_days: int = Field(30, alias="AUTH_SESSION_DAYS")

    # Monetisation kill switch. While we're still polishing the product
    # and using it internally, billing enforcement stays OFF — every
    # search succeeds regardless of ``queries_limit``. When we flip this
    # on (BILLING_ENFORCED=true in Railway vars) the existing quota
    # machinery starts gating again, no code changes needed.
    billing_enforced: bool = Field(False, alias="BILLING_ENFORCED")

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

    Deferred until first call so pydantic validation errors surface after
    logging is configured — instead of crashing silently at import time.
    """
    return Settings()  # type: ignore[call-arg]
