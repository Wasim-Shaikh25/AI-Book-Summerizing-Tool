"""JWT creation and validation."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import jwt

from auth.config import get_auth_settings


def create_access_token(user_id: str, email: str, extra: dict[str, Any] | None = None) -> str:
    settings = get_auth_settings()
    payload: dict[str, Any] = {
        "sub": user_id,
        "email": email,
        "exp": datetime.now(timezone.utc) + timedelta(days=settings.jwt_expire_days),
        "iat": datetime.now(timezone.utc),
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict[str, Any]:
    settings = get_auth_settings()
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
