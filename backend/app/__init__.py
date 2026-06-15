"""
App package shim — FastAPI layer.

Incremental rename target for ``backend/api/``.
"""

from api.main import app

__all__ = ["app"]
