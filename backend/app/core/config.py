from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    DATABASE_URL: str
    MIGRATION_DATABASE_URL: str | None = None

    CORS_ORIGINS: list[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]

    OIDC_ISSUER: str | None = None
    OIDC_AUDIENCE: str | None = None
    OIDC_JWKS_URL: str | None = None
    OIDC_JWKS_TIMEOUT_SECONDS: float = 5.0
    # Prefix of the custom claims that carry email, email_verified and
    # name in the access token (an Auth0 Action adds them). Empty means
    # the standard claim names.
    OIDC_CLAIMS_NAMESPACE: str | None = None

    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
