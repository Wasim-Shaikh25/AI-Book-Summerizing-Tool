"""Simple in-memory rate limiting per client IP."""

from __future__ import annotations

import time
from collections import defaultdict, deque

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from auth.config import get_auth_settings


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app) -> None:
        super().__init__(app)
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    async def dispatch(self, request: Request, call_next):
        if not request.url.path.startswith("/api/") or request.url.path == "/api/health":
            return await call_next(request)

        settings = get_auth_settings()
        client = request.client.host if request.client else "unknown"
        now = time.time()
        window = settings.rate_limit_window_seconds
        bucket = self._hits[client]

        while bucket and now - bucket[0] > window:
            bucket.popleft()

        if len(bucket) >= settings.rate_limit_requests:
            return Response("Rate limit exceeded", status_code=429)

        bucket.append(now)
        return await call_next(request)
