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

    # Invitation e-mails (docs/development/email-outbox.md).
    FRONTEND_BASE_URL: str = "http://localhost:3000"
    EMAIL_SENDER: str = "console"
    EMAIL_FROM: str = "Enterprise Knowledge AI <no-reply@localhost>"
    # Login of the outbox dispatcher; it must hold the eka_mailer role.
    MAILER_DATABASE_URL: str | None = None

    # Login of the background worker; it must hold the eka_worker role
    # (docs/development/background-jobs.md).
    WORKER_DATABASE_URL: str | None = None

    # Connection credentials (ADR-007). The API needs only the public
    # key; the private key belongs to the worker.
    CREDENTIALS_MASTER_PUBLIC_KEY: str | None = None
    CREDENTIALS_MASTER_PRIVATE_KEY: str | None = None

    # Object storage for document snapshots (ADR-004, docs/development/
    # sync.md). "local" is for development; S3 comes with hosting.
    STORAGE_BACKEND: str = "local"
    LOCAL_STORAGE_PATH: str = "var/storage"

    # Google Drive (docs/development/google-drive.md). The OAuth client
    # is the platform's own; each connection's authorization is sealed
    # in the credential store (ADR-007). The API and the worker both
    # need the client id and secret.
    GOOGLE_OAUTH_CLIENT_ID: str | None = None
    GOOGLE_OAUTH_CLIENT_SECRET: str | None = None
    # Where Google sends the browser back; empty means
    # FRONTEND_BASE_URL + /connections/google/callback.
    GOOGLE_OAUTH_REDIRECT_URI: str | None = None
    GOOGLE_DRIVE_SCOPE: str = (
        "https://www.googleapis.com/auth/drive.readonly"
    )
    # Signs the OAuth state: a long random value, API only.
    OAUTH_STATE_SECRET: str | None = None

    # Database connectors (docs/development/postgresql-connector.md).
    # Private and local addresses are refused unless this is true;
    # development only.
    DATABASE_CONNECTOR_ALLOW_PRIVATE_HOSTS: bool = False

    # Embeddings (docs/development/embeddings.md): fastembed runs
    # intfloat/multilingual-e5-small locally; hashing is for tests;
    # none turns search by meaning off.
    EMBEDDING_PROVIDER: str = "fastembed"
    EMBEDDING_CACHE_DIR: str = "var/models"

    # Reranking (docs/development/reranking.md): fastembed runs
    # BAAI/bge-reranker-v2-m3 (INT8) locally, in EMBEDDING_CACHE_DIR;
    # overlap is for tests; none turns it off.
    RERANK_PROVIDER: str = "fastembed"
    # How many of the first results it reads, and how many characters of
    # each (0 = the whole passage). Measured in AI-2b: 10 x 600 is the
    # only setting within 1.5 s on a laptop CPU. Off unless rerank=true.
    RERANK_CANDIDATES: int = 10
    RERANK_MAX_CHARS: int = 600

    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
