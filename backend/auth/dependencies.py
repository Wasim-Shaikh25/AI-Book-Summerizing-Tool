"""FastAPI auth dependencies."""

from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from auth.config import get_auth_settings
from auth.jwt_utils import decode_access_token
from storage.user_repository import UserRecord, UserRepository

_bearer = HTTPBearer(auto_error=False)

DEV_PROVIDER = "guest"
DEV_PROVIDER_USER_ID = "local-dev-user"


def get_dev_user() -> UserRecord:
    return UserRepository().upsert_oauth_user(
        provider=DEV_PROVIDER,
        provider_user_id=DEV_PROVIDER_USER_ID,
        email="dev@local.app",
        display_name="Local User",
        avatar_url=None,
    )


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> UserRecord:
    if not get_auth_settings().auth_enabled:
        return get_dev_user()

    if not credentials or not credentials.credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    try:
        payload = decode_access_token(credentials.credentials)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")

    user = UserRepository().get_by_id(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user
