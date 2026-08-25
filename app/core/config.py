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

    s3_endpoint_url: str | None = None
    s3_access_key_id: str | None = None
    s3_secret_access_key: str | None = None
    s3_bucket: str | None = None
    s3_region: str = "auto"
    media_public_base_url: str | None = None

    default_page_size: int = 20
    max_page_size: int = 100

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"

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
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
