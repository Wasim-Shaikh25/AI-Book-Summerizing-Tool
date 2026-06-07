"""OAuth login and callback routes."""

from __future__ import annotations

from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import RedirectResponse

from auth.config import get_auth_settings, oauth_provider_ready
from auth.jwt_utils import create_access_token
from auth.providers.oauth_providers import (
    AppleOAuthProvider,
    FacebookOAuthProvider,
    GoogleOAuthProvider,
    new_oauth_state,
)
from api.schemas import AuthConfigResponse, UserProfile
from auth.dependencies import get_current_user, get_dev_user
from storage.user_repository import UserRecord, UserRepository
from fastapi import Depends

router = APIRouter(prefix="/auth", tags=["auth"])

_PROVIDERS = {
    "google": GoogleOAuthProvider(),
    "apple": AppleOAuthProvider(),
    "facebook": FacebookOAuthProvider(),
}


@router.get("/config", response_model=AuthConfigResponse)
def auth_config() -> AuthConfigResponse:
    return AuthConfigResponse(auth_enabled=get_auth_settings().auth_enabled)


@router.post("/guest", response_model=UserProfile)
def login_as_guest() -> UserProfile:
    if get_auth_settings().auth_enabled:
        raise HTTPException(status_code=403, detail="Guest login is disabled. Set AUTH_ENABLED=false in .env.")
    user = get_dev_user()
    return UserProfile(
        user_id=user.user_id,
        email=user.email,
        display_name=user.display_name,
        provider=user.provider,
        avatar_url=user.avatar_url,
    )


@router.get("/{provider}/login")
async def oauth_login(provider: str):
    if provider not in _PROVIDERS:
        raise HTTPException(status_code=404, detail="Unknown provider")
    ready, msg = oauth_provider_ready(provider)
    if not ready:
        raise HTTPException(status_code=503, detail=msg)
    state = new_oauth_state()
    url = _PROVIDERS[provider].get_login_url(state)
    return RedirectResponse(url)


@router.get("/{provider}/callback")
async def oauth_callback(
    provider: str,
    code: str = Query(...),
    state: str | None = Query(None),
    user: str | None = Query(None),
):
    if provider not in _PROVIDERS:
        raise HTTPException(status_code=404, detail="Unknown provider")

    try:
        if provider == "apple":
            info = await _PROVIDERS["apple"].exchange_code(code, user_json=user)
        else:
            info = await _PROVIDERS[provider].exchange_code(code)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"OAuth failed: {exc}") from exc

    user_record = UserRepository().upsert_oauth_user(
        provider=info.provider,
        provider_user_id=info.provider_user_id,
        email=info.email,
        display_name=info.display_name,
        avatar_url=info.avatar_url,
    )
    token = create_access_token(user_record.user_id, user_record.email)
    settings = get_auth_settings()
    redirect = f"{settings.frontend_url}/auth/callback?{urlencode({'token': token})}"
    return RedirectResponse(redirect)


@router.get("/me", response_model=UserProfile)
def me(current: UserRecord = Depends(get_current_user)) -> UserProfile:
    return UserProfile(
        user_id=current.user_id,
        email=current.email,
        display_name=current.display_name,
        provider=current.provider,
        avatar_url=current.avatar_url,
    )
