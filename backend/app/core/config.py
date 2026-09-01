from functools import lru_cache
from urllib.parse import urlparse

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Every optional credential in .env.example is listed with an empty value, which
# is how a reader is told the key exists and is not set. Pydantic would hand
# those through as "" rather than None, and "" is not the same as unset.
BLANK_MEANS_UNSET = (
    "openai_api_key",
    "pexels_api_key",
    "fanart_api_key",
    "s3_endpoint_url",
    "s3_access_key_id",
    "s3_secret_access_key",
    "s3_bucket",
    "media_public_base_url",
)


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

    # ------------------------------------------------------------- sign-in
    # Accounts are created by an administrator, never by a visitor: there is no
    # registration endpoint. The first one is made with `canilarpit create-user`.
    #
    # A session is a random opaque string in an HttpOnly cookie, stored here
    # only as a hash. Unlike a signed token it can be revoked and is refused on
    # the next request, so "sign out everywhere" means it.
    session_lifetime_seconds: int = 60 * 60 * 24 * 14
    # Non-password identities: the local development bypass, and the seeder.
    # Refused outright in production, twice over.
    dev_auth_bypass: bool = False

    # Failed sign-ins per client per minute, and per account per minute. Both,
    # because a password can be guessed from many addresses and one address can
    # try many accounts. Cleared as soon as a sign-in succeeds.
    auth_failures_per_minute: int = 20
    account_failures_per_minute: int = 10
    # A ceiling on the admin surface as a whole, per client per minute. Loose
    # enough that `npm run db:upload` replaying the whole catalog does not trip
    # it — that is a legitimate burst of writes — and tight enough that a
    # drained session or a walk of the route table is not free.
    admin_requests_per_minute: int = 600

    # Swagger and the schema are a free map of the admin surface. They are
    # always off in production regardless of this; this only turns them off
    # somewhere else as well.
    expose_api_docs: bool = True
    # Host header allowlist. Empty means the middleware is not installed at
    # all, because a wrong list here 400s every request including health checks.
    trusted_hosts: list[str] = Field(default_factory=list)
    hsts_max_age_seconds: int = 31_536_000
    # Flip to true to watch the content policy in the console without it
    # blocking anything. The escape hatch for a policy that turns out too tight.
    csp_report_only: bool = False
    # Extra origins the panel may load code from and talk to. Empty by default:
    # sign-in is served by this application, so nothing third-party is needed.
    csp_extra_origins: list[str] = Field(default_factory=list)

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

    @field_validator(*BLANK_MEANS_UNSET, mode="before")
    @classmethod
    def blank_is_unset(cls, value: object) -> object:
        """`KEY=` in an env file means "not set", not "set to empty"."""
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"

    @property
    def site_origin(self) -> str:
        """The base URL without a trailing slash, so joins never double one."""
        return self.site_base_url.rstrip("/")

    @property
    def api_docs_enabled(self) -> bool:
        """Never in production, whatever the setting says."""
        return self.expose_api_docs and not self.is_production

    @property
    def admin_script_origins(self) -> list[str]:
        """Origins the admin panel may load code from, beyond its own.

        Empty unless a deployment adds some. Sign-in is a form this application
        serves, so the panel needs nothing third-party — which is why its
        content policy can stay as narrow as the reading interface's.
        """
        return [origin for origin in dict.fromkeys(self.csp_extra_origins) if origin]

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
        if self.is_production and self.submission_secret == "dev-only-change-me":
            raise ValueError("SUBMISSION_SECRET must be set in production")
        if self.session_lifetime_seconds <= 0:
            raise ValueError("SESSION_LIFETIME_SECONDS must be positive")
        return self

    @model_validator(mode="after")
    def require_production_origins_to_be_real(self) -> "Settings":
        """No wildcards and no cleartext on a deployment that carries tokens.

        `allow_credentials` with a wildcard origin is the classic way to hand
        every site on the internet an authenticated admin session, so it is
        refused here rather than left to the browser to decline.
        """
        if not self.is_production:
            return self

        for origin in self.frontend_origins:
            if origin == "*":
                raise ValueError(
                    "FRONTEND_ORIGINS cannot contain '*' in production: the API sends "
                    "credentials, and a wildcard origin would share them with anybody"
                )
            if not origin.startswith("https://"):
                raise ValueError(f"FRONTEND_ORIGINS must be https in production; got {origin!r}")

        if urlparse(self.site_base_url).scheme != "https":
            raise ValueError("SITE_BASE_URL must be https in production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
