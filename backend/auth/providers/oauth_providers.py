"""OAuth provider implementations."""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import httpx
import jwt

from auth.config import get_auth_settings


@dataclass
class OAuthUserInfo:
    provider: str
    provider_user_id: str
    email: str
    display_name: str
    avatar_url: str | None = None


class GoogleOAuthProvider:
    AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
    TOKEN_URL = "https://oauth2.googleapis.com/token"
    USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"
    SCOPES = ["openid", "email", "profile"]

    def get_login_url(self, state: str) -> str:
        settings = get_auth_settings()
        params = {
            "client_id": settings.google_client_id,
            "redirect_uri": settings.google_redirect_uri,
            "response_type": "code",
            "scope": " ".join(self.SCOPES),
            "state": state,
            "access_type": "online",
            "prompt": "select_account",
        }
        return f"{self.AUTH_URL}?{urlencode(params)}"

    async def exchange_code(self, code: str) -> OAuthUserInfo:
        settings = get_auth_settings()
        async with httpx.AsyncClient() as client:
            token_resp = await client.post(
                self.TOKEN_URL,
                data={
                    "code": code,
                    "client_id": settings.google_client_id,
                    "client_secret": settings.google_client_secret,
                    "redirect_uri": settings.google_redirect_uri,
                    "grant_type": "authorization_code",
                },
            )
            token_resp.raise_for_status()
            access_token = token_resp.json()["access_token"]

            user_resp = await client.get(
                self.USERINFO_URL,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            user_resp.raise_for_status()
            data = user_resp.json()

        return OAuthUserInfo(
            provider="google",
            provider_user_id=str(data["id"]),
            email=data.get("email") or f"{data['id']}@google.oauth",
            display_name=data.get("name") or data.get("email") or "Google User",
            avatar_url=data.get("picture"),
        )


class FacebookOAuthProvider:
    AUTH_URL = "https://www.facebook.com/v19.0/dialog/oauth"
    TOKEN_URL = "https://graph.facebook.com/v19.0/oauth/access_token"
    USERINFO_URL = "https://graph.facebook.com/me"
    SCOPES = ["email", "public_profile"]

    def get_login_url(self, state: str) -> str:
        settings = get_auth_settings()
        params = {
            "client_id": settings.facebook_app_id,
            "redirect_uri": settings.facebook_redirect_uri,
            "response_type": "code",
            "scope": ",".join(self.SCOPES),
            "state": state,
        }
        return f"{self.AUTH_URL}?{urlencode(params)}"

    async def exchange_code(self, code: str) -> OAuthUserInfo:
        settings = get_auth_settings()
        async with httpx.AsyncClient() as client:
            token_resp = await client.get(
                self.TOKEN_URL,
                params={
                    "client_id": settings.facebook_app_id,
                    "client_secret": settings.facebook_app_secret,
                    "redirect_uri": settings.facebook_redirect_uri,
                    "code": code,
                },
            )
            token_resp.raise_for_status()
            access_token = token_resp.json()["access_token"]

            user_resp = await client.get(
                self.USERINFO_URL,
                params={"fields": "id,name,email,picture", "access_token": access_token},
            )
            user_resp.raise_for_status()
            data = user_resp.json()

        picture = None
        if isinstance(data.get("picture"), dict):
            picture = data["picture"].get("data", {}).get("url")

        return OAuthUserInfo(
            provider="facebook",
            provider_user_id=str(data["id"]),
            email=data.get("email") or f"{data['id']}@facebook.oauth",
            display_name=data.get("name") or "Facebook User",
            avatar_url=picture,
        )


class AppleOAuthProvider:
    AUTH_URL = "https://appleid.apple.com/auth/authorize"
    TOKEN_URL = "https://appleid.apple.com/auth/token"
    SCOPES = ["name", "email"]

    def _client_secret(self) -> str:
        settings = get_auth_settings()
        if not all(
            [
                settings.apple_client_id,
                settings.apple_team_id,
                settings.apple_key_id,
                settings.apple_private_key_path,
            ]
        ):
            raise RuntimeError("Apple OAuth is not configured")

        with open(settings.apple_private_key_path, encoding="utf-8") as f:
            private_key = f.read()

        now = int(time.time())
        headers = {"kid": settings.apple_key_id, "alg": "ES256"}
        payload = {
            "iss": settings.apple_team_id,
            "iat": now,
            "exp": now + 86400 * 180,
            "aud": "https://appleid.apple.com",
            "sub": settings.apple_client_id,
        }
        return jwt.encode(payload, private_key, algorithm="ES256", headers=headers)

    def get_login_url(self, state: str) -> str:
        settings = get_auth_settings()
        params = {
            "client_id": settings.apple_client_id,
            "redirect_uri": settings.apple_redirect_uri,
            "response_type": "code",
            "response_mode": "query",
            "scope": " ".join(self.SCOPES),
            "state": state,
        }
        return f"{self.AUTH_URL}?{urlencode(params)}"

    async def exchange_code(self, code: str, user_json: str | None = None) -> OAuthUserInfo:
        settings = get_auth_settings()
        async with httpx.AsyncClient() as client:
            token_resp = await client.post(
                self.TOKEN_URL,
                data={
                    "client_id": settings.apple_client_id,
                    "client_secret": self._client_secret(),
                    "code": code,
                    "grant_type": "authorization_code",
                    "redirect_uri": settings.apple_redirect_uri,
                },
            )
            token_resp.raise_for_status()
            id_token = token_resp.json()["id_token"]
            claims = jwt.decode(id_token, options={"verify_signature": False})

        display_name = "Apple User"
        email = claims.get("email") or f"{claims['sub']}@apple.oauth"
        if user_json:
            try:
                user_data = json.loads(user_json)
                name = user_data.get("name", {})
                first = name.get("firstName", "")
                last = name.get("lastName", "")
                combined = f"{first} {last}".strip()
                if combined:
                    display_name = combined
            except json.JSONDecodeError:
                pass

        return OAuthUserInfo(
            provider="apple",
            provider_user_id=str(claims["sub"]),
            email=email,
            display_name=display_name,
            avatar_url=None,
        )


def new_oauth_state() -> str:
    return uuid.uuid4().hex
