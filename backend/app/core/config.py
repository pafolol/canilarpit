from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "Can I LARP It API"
    app_env: str = "development"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/canilarpit"
    frontend_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://localhost:5173"]
    )

    clerk_issuer: str | None = None
    clerk_jwks_url: str | None = None
    clerk_webhook_secret: str | None = None
    clerk_audience: str | None = None
    clerk_authorized_parties: list[str] = Field(default_factory=list)
    dev_auth_bypass: bool = False

    # Guide generation. The admin panel degrades to manual authoring without these.
    openai_api_key: str | None = None
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4.1"
    openai_timeout_seconds: float = 300.0
    ai_max_repair_attempts: int = 2
    ai_verify_sources: bool = True
    # Published gpt-4.1 rates, in USD per million tokens. Override when the model changes.
    openai_input_usd_per_million: float = 2.0
    openai_output_usd_per_million: float = 8.0

    # Imagery. Wikimedia, TVmaze, AniList and Jikan need no key; the rest do.
    # TMDB is deliberately absent: it charges for commercial use.
    pexels_api_key: str | None = None
    fanart_api_key: str | None = None
    image_results_per_query: int = 8

    s3_endpoint_url: str | None = None
    s3_access_key_id: str | None = None
    s3_secret_access_key: str | None = None
    s3_bucket: str | None = None
    s3_region: str = "auto"
    media_public_base_url: str | None = None

    # ------------------------------------------------------- reader submissions
    # Signs the form token and derives the anonymous client hash. Rotating it
    # invalidates open forms and every stored client hash, which is the intended
    # way to reset a block list.
    submission_secret: str = "dev-only-change-me"
    # True only when the app really is behind a proxy that sets the header;
    # otherwise anybody can mint a fresh identity per request by setting it.
    trust_forwarded_for: bool = False
    # Two different jobs. The request limits are a flood guard and count every
    # attempt, including ones rejected for a bad token, so they are loose enough
    # that a person who mistypes twice is not locked out for an hour. What
    # actually bounds the editorial queue is max_pending, which counts rows and
    # frees up as an editor works through them.
    submissions_per_hour: str = "20/hour"
    submissions_per_day: str = "60/day"
    submission_max_pending: int = 3
    submission_min_seconds: float = 4.0
    submission_token_ttl_seconds: int = 3600
    submission_min_notes: int = 80
    submission_max_links: int = 2

    # ------------------------------------------------------------ the public site
    # Absolute URLs in the sitemap and in the Open Graph tags, which have to be
    # absolute for a preview to resolve them.
    site_base_url: str = "http://localhost:8000"
    # Where `npm run build` puts the app. When it is absent — the normal dev case,
    # where Vite serves the frontend — the API serves no HTML at all.
    frontend_dist: str = "frontend/dist"

    # One counted view per client per guide per window. Shorter and the number is
    # a refresh count; longer and a genuine second reading never registers.
    view_dedupe_seconds: int = 1800
    # How long a heartbeat keeps somebody on the site, and the window the strip
    # counts. Sweeping at the longer one leaves a little slack for a missed beat.
    presence_window_seconds: int = 120
    presence_ttl_seconds: int = 300

    default_page_size: int = 20
    max_page_size: int = 100

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"

    @property
    def site_origin(self) -> str:
        """The base URL without a trailing slash, so joins never double one."""
        return self.site_base_url.rstrip("/")

    @property
    def ai_configured(self) -> bool:
        return bool(self.openai_api_key)

    @property
    def stock_configured(self) -> bool:
        """Kept for the settings validator's sake; the registry is the real answer."""
        return bool(self.pexels_api_key)

    @property
    def storage_configured(self) -> bool:
        return all(
            (
                self.s3_access_key_id,
                self.s3_secret_access_key,
                self.s3_bucket,
            )
        )

    @model_validator(mode="after")
    def prevent_production_auth_bypass(self) -> "Settings":
        if self.is_production and self.dev_auth_bypass:
            raise ValueError("DEV_AUTH_BYPASS cannot be enabled in production")
        if self.is_production and (not self.clerk_issuer or not self.clerk_jwks_url):
            raise ValueError("Clerk issuer and JWKS URL are required in production")
        if self.is_production and not (
            self.clerk_audience or self.clerk_authorized_parties
        ):
            raise ValueError(
                "Production Clerk auth requires an audience or authorized-party allowlist"
            )
        if self.is_production and self.submission_secret == "dev-only-change-me":
            raise ValueError("SUBMISSION_SECRET must be set in production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
