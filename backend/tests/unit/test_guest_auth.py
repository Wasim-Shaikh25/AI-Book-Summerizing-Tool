"""Tests for guest-mode auth (anonymous access when OAuth is enabled)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND_ROOT))

from api.routes import auth as auth_routes  # noqa: E402


class _Settings:
    def __init__(self, *, auth_enabled: bool, allow_guest: bool) -> None:
        self.auth_enabled = auth_enabled
        self.allow_guest = allow_guest


class _UserRecord:
    def __init__(self, uid: str) -> None:
        self.user_id = uid
        self.email = f"{uid}@guest.local"
        self.display_name = "Guest"
        self.provider = "guest"
        self.avatar_url = None


def _patch_repo(monkeypatch):
    created = {}

    class _Repo:
        def upsert_oauth_user(self, *, provider, provider_user_id, email, display_name, avatar_url):
            created["provider_user_id"] = provider_user_id
            return _UserRecord(provider_user_id)

    monkeypatch.setattr(auth_routes, "UserRepository", _Repo)
    return created


def test_config_exposes_allow_guest(monkeypatch):
    monkeypatch.setattr(
        auth_routes, "get_auth_settings", lambda: _Settings(auth_enabled=True, allow_guest=True)
    )
    cfg = auth_routes.auth_config()
    assert cfg.auth_enabled is True
    assert cfg.allow_guest is True


def test_guest_issues_token_when_auth_enabled(monkeypatch):
    monkeypatch.setattr(
        auth_routes, "get_auth_settings", lambda: _Settings(auth_enabled=True, allow_guest=True)
    )
    _patch_repo(monkeypatch)
    monkeypatch.setattr(auth_routes, "create_access_token", lambda uid, email, extra=None: "guest-jwt")

    resp = auth_routes.login_as_guest()
    assert resp.token == "guest-jwt"
    assert resp.user.provider == "guest"
    assert resp.user.user_id.startswith("guest-")


def test_guest_blocked_when_disabled(monkeypatch):
    monkeypatch.setattr(
        auth_routes, "get_auth_settings", lambda: _Settings(auth_enabled=True, allow_guest=False)
    )
    with pytest.raises(Exception) as exc:
        auth_routes.login_as_guest()
    assert "403" in str(getattr(exc.value, "status_code", "")) or "disabled" in str(exc.value).lower()


def test_guest_no_token_when_auth_disabled(monkeypatch):
    monkeypatch.setattr(
        auth_routes, "get_auth_settings", lambda: _Settings(auth_enabled=False, allow_guest=True)
    )
    monkeypatch.setattr(auth_routes, "get_dev_user", lambda: _UserRecord("local-dev-user"))
    resp = auth_routes.login_as_guest()
    assert resp.token is None
    assert resp.user.provider == "guest"
