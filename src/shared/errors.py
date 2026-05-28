"""Shared configuration errors."""

from __future__ import annotations


class ConfigError(Exception):
    def __init__(self, message: str, *, ctx: dict | None = None) -> None:
        super().__init__(message)
        self.ctx = ctx or {}
