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
from api.schemas import AuthConfigResponse, GuestSessionResponse, UserProfile
from auth.dependencies import get_current_user, get_dev_user
from storage.user_repository import UserRecord, UserRepository
from fastapi import Depends
import uuid

router = APIRouter(prefix="/auth", tags=["auth"])

_PROVIDERS = {
    "google": GoogleOAuthProvider(),
    "apple": AppleOAuthProvider(),
    "facebook": FacebookOAuthProvider(),
}


@router.get("/config", response_model=AuthConfigResponse)
def auth_config() -> AuthConfigResponse:
    settings = get_auth_settings()
    return AuthConfigResponse(
        auth_enabled=settings.auth_enabled,
        allow_guest=settings.allow_guest,
    )


@router.post("/guest", response_model=GuestSessionResponse)
def login_as_guest() -> GuestSessionResponse:
    settings = get_auth_settings()

    # Auth off: everyone shares the local dev/guest identity (no token needed).
    if not settings.auth_enabled:
        user = get_dev_user()
        return GuestSessionResponse(user=_to_profile(user), token=None)

    # Auth on but guest allowed: mint an isolated, persisted guest + short-lived JWT.
    if not settings.allow_guest:
        raise HTTPException(
            status_code=403,
            detail="Guest access is disabled. Set ALLOW_GUEST=true (or AUTH_ENABLED=false) in .env.",
        )
    guest_id = uuid.uuid4().hex[:12]
    user = UserRepository().upsert_oauth_user(
        provider="guest",
        provider_user_id=f"guest-{guest_id}",
        email=f"guest-{guest_id}@guest.local",
        display_name="Guest",
        avatar_url=None,
    )
    token = create_access_token(user.user_id, user.email, extra={"guest": True})
    return GuestSessionResponse(user=_to_profile(user), token=token)


def _to_profile(user: UserRecord) -> UserProfile:
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
