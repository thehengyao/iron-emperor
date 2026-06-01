"""
Request middleware — tracing, timing, concurrency limiting.

Adds X-Request-Id and X-Duration-Ms response headers.
Limits concurrent builds to prevent Opus rate-limit storms.
"""
import asyncio
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response


class RequestTracingMiddleware(BaseHTTPMiddleware):
    """Adds request ID and duration to every response."""

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = str(uuid.uuid4())[:8]
        t0 = time.monotonic()
        response = await call_next(request)
        duration_ms = int((time.monotonic() - t0) * 1000)
        response.headers["X-Request-Id"] = request_id
        response.headers["X-Duration-Ms"] = str(duration_ms)
        return response


class ConcurrencyLimitMiddleware(BaseHTTPMiddleware):
    """Limits concurrent pipeline builds to prevent Opus rate limits."""

    def __init__(self, app, max_concurrent: int = 2, build_paths: set[str] | None = None):
        super().__init__(app)
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.build_paths = build_paths or {"/build", "/build/stream", "/a2a/build"}

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.url.path not in self.build_paths:
            return await call_next(request)

        if not self.semaphore._value:
            return JSONResponse(
                status_code=429,
                content={"error": "Too many concurrent builds. Try again shortly."},
                headers={"Retry-After": "30"},
            )

        async with self.semaphore:
            return await call_next(request)
