"""Auth and API configuration."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
_PROJECT_ROOT = Path(os.getenv("PROJECT_ROOT", str(_BACKEND_ROOT.parent)))
_ENV_FILE = _PROJECT_ROOT / ".env"


class AuthSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE) if _ENV_FILE.exists() else None,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    jwt_secret: str = os.getenv("JWT_SECRET", "dev-secret-change-in-production")
    jwt_algorithm: str = "HS256"
    jwt_expire_days: int = int(os.getenv("JWT_EXPIRE_DAYS", "7"))

    frontend_url: str = os.getenv("FRONTEND_URL", "http://localhost:5173")
    api_base_url: str = os.getenv("API_BASE_URL", "http://localhost:8000")
    # Comma-separated extra origins allowed by CORS (e.g. a prod domain behind a proxy).
    cors_extra_origins: str = os.getenv("CORS_EXTRA_ORIGINS", "")

    @property
    def cors_origins(self) -> list[str]:
        """Allowed CORS origins: localhost dev hosts + FRONTEND_URL + extras."""
        origins = [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ]
        if self.frontend_url:
            origins.append(self.frontend_url.rstrip("/"))
        for extra in self.cors_extra_origins.split(","):
            extra = extra.strip().rstrip("/")
            if extra:
                origins.append(extra)
        seen: set[str] = set()
        unique: list[str] = []
        for origin in origins:
            if origin not in seen:
                seen.add(origin)
                unique.append(origin)
        return unique

    chat_docx_char_limit: int = int(os.getenv("CHAT_DOCX_CHAR_LIMIT", "4000"))
    max_upload_mb: int = int(os.getenv("MAX_UPLOAD_MB", "100"))
    rate_limit_requests: int = int(os.getenv("RATE_LIMIT_REQUESTS", "60"))
    rate_limit_window_seconds: int = int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60"))

    auth_enabled: bool = True
    # Allow anonymous "Continue as guest" access even when OAuth auth is enabled.
    # Each guest gets an isolated, persisted guest user + short-lived JWT.
    allow_guest: bool = os.getenv("ALLOW_GUEST", "true").strip().lower() in {"1", "true", "yes", "on"}

    google_client_id: str = ""
    google_client_secret: str = os.getenv("GOOGLE_CLIENT_SECRET", "")
    google_redirect_uri: str = os.getenv(
        "GOOGLE_REDIRECT_URI", "http://localhost:8000/api/auth/google/callback"
    )

    apple_client_id: str = os.getenv("APPLE_CLIENT_ID", "")
    apple_team_id: str = os.getenv("APPLE_TEAM_ID", "")
    apple_key_id: str = os.getenv("APPLE_KEY_ID", "")
    apple_private_key_path: str = os.getenv("APPLE_PRIVATE_KEY_PATH", "")
    apple_redirect_uri: str = os.getenv(
        "APPLE_REDIRECT_URI", "http://localhost:8000/api/auth/apple/callback"
    )

    facebook_app_id: str = os.getenv("FACEBOOK_APP_ID", "")
    facebook_app_secret: str = os.getenv("FACEBOOK_APP_SECRET", "")
    facebook_redirect_uri: str = os.getenv(
        "FACEBOOK_REDIRECT_URI", "http://localhost:8000/api/auth/facebook/callback"
    )


@lru_cache
def get_auth_settings() -> AuthSettings:
    return AuthSettings()


def oauth_provider_ready(provider: str) -> tuple[bool, str]:
    """Return (ready, error_message)."""
    s = get_auth_settings()
    if provider == "google":
        if not s.google_client_id or not s.google_client_secret:
            return False, "Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in the repo root .env file."
        return True, ""
    if provider == "facebook":
        if not s.facebook_app_id or not s.facebook_app_secret:
            return False, "Set FACEBOOK_APP_ID and FACEBOOK_APP_SECRET in the repo root .env file."
        return True, ""
    if provider == "apple":
        if not all([s.apple_client_id, s.apple_team_id, s.apple_key_id, s.apple_private_key_path]):
            return False, "Set APPLE_CLIENT_ID, APPLE_TEAM_ID, APPLE_KEY_ID, and APPLE_PRIVATE_KEY_PATH in .env."
        return True, ""
    return False, "Unknown provider"
