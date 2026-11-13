import jwt
from jwt import PyJWKClient

from app.core.config import settings


ALLOWED_ALGORITHMS = ["RS256"]

_jwks_client: PyJWKClient | None = None


def get_jwks_client() -> PyJWKClient:
    global _jwks_client

    if not settings.OIDC_JWKS_URL:
        raise RuntimeError("OIDC JWKS URL is not configured")

    if _jwks_client is None:
        _jwks_client = PyJWKClient(
            settings.OIDC_JWKS_URL,
            timeout=settings.OIDC_JWKS_TIMEOUT_SECONDS,
        )

    return _jwks_client


def verify_access_token(token: str) -> dict:
    required_settings = {
        "OIDC_ISSUER": settings.OIDC_ISSUER,
        "OIDC_AUDIENCE": settings.OIDC_AUDIENCE,
        "OIDC_JWKS_URL": settings.OIDC_JWKS_URL,
    }

    missing_settings = [
        name for name, value in required_settings.items() if not value
    ]

    if missing_settings:
        raise RuntimeError(
            f"OIDC configuration is incomplete: {', '.join(missing_settings)}"
        )

    jwks_client = get_jwks_client()
    signing_key = jwks_client.get_signing_key_from_jwt(token)

    payload = jwt.decode(
        token,
        signing_key.key,
        algorithms=ALLOWED_ALGORITHMS,
        issuer=settings.OIDC_ISSUER,
        audience=settings.OIDC_AUDIENCE,
        options={
            "require": ["exp", "iss", "aud", "sub"],
        },
    )

    return payload