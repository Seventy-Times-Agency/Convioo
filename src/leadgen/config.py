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
    # ``json`` for production (Railway / log shippers parse it cleanly),
    # ``text`` for local dev so a human can read the lines. Anything
    # else falls back to ``text``.
    log_format: str = Field("text", alias="LOG_FORMAT")
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

    # Invite code that gates public registration. Empty = registration
    # is open (legacy behavior, dev-friendly). When set on Railway, the
    # /api/v1/auth/register endpoint requires the same value in the
    # ``registration_password`` body field — otherwise it returns 403.
    # Used to keep the production site closed while still demoing it
    # to invited people.
    registration_password: str = Field("", alias="REGISTRATION_PASSWORD")

    # Monetisation kill switch. While we're still polishing the product
    # and using it internally, billing enforcement stays OFF — every
    # search succeeds regardless of ``queries_limit``. When we flip this
    # on (BILLING_ENFORCED=true in Railway vars) the existing quota
    # machinery starts gating again, no code changes needed.
    billing_enforced: bool = Field(False, alias="BILLING_ENFORCED")

    # Multi-source: query OpenStreetMap (Nominatim + Overpass) alongside
    # Google Places when the niche has a known OSM tag mapping. Free,
    # no key needed, but soft-rate-limited — set OSM_ENABLED=false on
    # Railway if Overpass starts misbehaving and you want a quick kill
    # switch without redeploying.
    osm_enabled: bool = Field(True, alias="OSM_ENABLED")

    # Yelp Fusion. Strong US/CA/UK coverage; free tier is 5k req/day.
    # Niches activate Yelp only when they have ``yelp_categories`` set
    # in the taxonomy YAML, so an empty key just disables the source.
    # Toggle ``YELP_ENABLED=false`` to skip Yelp without rotating the key.
    yelp_api_key: str = Field("", alias="YELP_API_KEY")
    yelp_enabled: bool = Field(True, alias="YELP_ENABLED")

    # Foursquare Places v3. Global coverage, free tier 950 calls/day.
    # Activates only when the niche has ``fsq_categories`` set in the
    # taxonomy YAML — same opt-in shape as Yelp.
    fsq_api_key: str = Field("", alias="FSQ_API_KEY")
    fsq_enabled: bool = Field(True, alias="FSQ_ENABLED")

    # Sentry. Empty DSN = SDK never initialises (zero overhead).
    # ``SENTRY_DSN_API`` is the backend project's ingest URL; the
    # frontend has its own ``NEXT_PUBLIC_SENTRY_DSN`` Next env var
    # consumed by the Sentry Next SDK directly.
    sentry_dsn_api: str = Field("", alias="SENTRY_DSN_API")
    # Per-environment label so dev errors don't pollute the prod
    # project.
    sentry_environment: str = Field(
        "production", alias="SENTRY_ENVIRONMENT"
    )
    # Trace sample rate. Keep modest in production; the SDK's hot
    # path is cheap but cumulative cost adds up at scale.
    sentry_traces_sample_rate: float = Field(
        0.1, alias="SENTRY_TRACES_SAMPLE_RATE"
    )

    # Encrypts integration tokens at rest (Notion, future Gmail OAuth
    # tokens, etc). Must be a Fernet-format key (44-char base64). When
    # unset locally we derive a deterministic dev key from a fixed seed
    # so the SQLite test harness keeps working — production deploys
    # MUST set this on Railway, otherwise restarting the container
    # invalidates every stored credential.
    fernet_key: str = Field("", alias="FERNET_KEY")

    # Stripe — when any of these are empty we run in "stage" mode:
    # ``/api/v1/billing/*`` endpoints respond with 503 instead of
    # crashing, so the rest of the API keeps working without the
    # billing keys configured. Set all four on Railway plus
    # ``STRIPE_TRIAL_DAYS`` (defaults to 14) to enable real payments.
    stripe_secret_key: str = Field("", alias="STRIPE_SECRET_KEY")
    stripe_webhook_secret: str = Field("", alias="STRIPE_WEBHOOK_SECRET")
    stripe_price_id_pro: str = Field("", alias="STRIPE_PRICE_ID_PRO")
    stripe_price_id_agency: str = Field("", alias="STRIPE_PRICE_ID_AGENCY")
    stripe_trial_days: int = Field(14, alias="STRIPE_TRIAL_DAYS")

    # Gmail OAuth — needed for outreach send-as-user. When the client
    # id / secret are empty the ``/api/v1/oauth/gmail/*`` endpoints
    # respond 503 instead of crashing. ``GOOGLE_OAUTH_REDIRECT_URI``
    # MUST match the redirect URI registered in Google Cloud Console
    # for the OAuth client; default is the Convioo prod path.
    google_oauth_client_id: str = Field("", alias="GOOGLE_OAUTH_CLIENT_ID")
    google_oauth_client_secret: str = Field(
        "", alias="GOOGLE_OAUTH_CLIENT_SECRET"
    )
    google_oauth_redirect_uri: str = Field(
        "https://convioo.com/api/v1/oauth/gmail/callback",
        alias="GOOGLE_OAUTH_REDIRECT_URI",
    )

    # HubSpot OAuth — push-to-CRM connector. 503-safe when unset
    # (mirroring Gmail / Stripe). Redirect URI MUST match the value
    # registered on the HubSpot app's "Auth" tab.
    hubspot_oauth_client_id: str = Field(
        "", alias="HUBSPOT_OAUTH_CLIENT_ID"
    )
    hubspot_oauth_client_secret: str = Field(
        "", alias="HUBSPOT_OAUTH_CLIENT_SECRET"
    )
    hubspot_oauth_redirect_uri: str = Field(
        "https://convioo.com/api/v1/integrations/hubspot/callback",
        alias="HUBSPOT_OAUTH_REDIRECT_URI",
    )

    # Pipedrive OAuth — push-to-CRM connector. 503-safe when unset.
    # Redirect URI MUST match the value registered on the Pipedrive
    # marketplace app's "OAuth & access scopes" tab.
    pipedrive_oauth_client_id: str = Field(
        "", alias="PIPEDRIVE_OAUTH_CLIENT_ID"
    )
    pipedrive_oauth_client_secret: str = Field(
        "", alias="PIPEDRIVE_OAUTH_CLIENT_SECRET"
    )
    pipedrive_oauth_redirect_uri: str = Field(
        "https://convioo.com/api/v1/integrations/pipedrive/callback",
        alias="PIPEDRIVE_OAUTH_REDIRECT_URI",
    )

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
