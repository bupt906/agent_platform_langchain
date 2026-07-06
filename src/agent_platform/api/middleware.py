"""安全与可观测性中间件。

提供:
- API Key 认证（Bearer Token 方式）
- 基于滑动窗口的速率限制
- 请求日志与耗时统计
"""

from __future__ import annotations

import logging
import time
from typing import Callable

from fastapi import HTTPException, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from agent_platform.config.settings import settings

logger = logging.getLogger("agent_platform.api")


# ── API Key 认证 ────────────────────────────────────────────────


class AuthMiddleware(BaseHTTPMiddleware):
    """Bearer Token 认证中间件。

    配置 Settings.api_key 后生效；不配置则跳过认证。
    """

    def __init__(self, app: ASGIApp, api_key: str | None = None) -> None:
        super().__init__(app)
        self._api_key = api_key or settings.api_key

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if not self._api_key:
            return await call_next(request)

        # 豁免健康检查端点
        if request.url.path == "/health":
            return await call_next(request)

        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer ") or auth[7:] != self._api_key:
            raise HTTPException(status_code=401, detail="未提供有效的 API Key")

        return await call_next(request)


# ── 速率限制 ────────────────────────────────────────────────────


class RateLimitMiddleware(BaseHTTPMiddleware):
    """基于滑动窗口的速率限制中间件。

    按客户端 IP 计数，超出限制返回 429。
    """

    def __init__(self, app: ASGIApp, max_per_minute: int | None = None) -> None:
        super().__init__(app)
        self._max = max_per_minute or settings.rate_limit_per_minute
        self._window_secs: float = 60.0
        self._buckets: dict[str, list[float]] = {}

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if self._max <= 0:
            return await call_next(request)

        # 豁免健康检查端点
        if request.url.path == "/health":
            return await call_next(request)

        client = request.client.host if request.client else "unknown"
        now = time.monotonic()

        if client not in self._buckets:
            self._buckets[client] = []

        # 清理过期记录
        cutoff = now - self._window_secs
        self._buckets[client] = [t for t in self._buckets[client] if t > cutoff]

        if len(self._buckets[client]) >= self._max:
            raise HTTPException(status_code=429, detail="请求过于频繁，请稍后重试")

        self._buckets[client].append(now)
        return await call_next(request)


# ── 可观测性 ────────────────────────────────────────────────────


class ObservabilityMiddleware(BaseHTTPMiddleware):
    """请求日志 + 耗时统计中间件。"""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        start = time.monotonic()
        response = await call_next(request)
        duration_ms = (time.monotonic() - start) * 1000

        logger.info(
            "%s %s → %d  %.1fms",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
        )
        return response
