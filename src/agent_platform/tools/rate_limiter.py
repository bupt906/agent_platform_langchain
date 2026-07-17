"""工具调用速率限制。

基于令牌桶算法的异步速率限制器，按工具名 + 全局两级限流。
"""

from __future__ import annotations

import asyncio
import logging
import time

logger = logging.getLogger(__name__)


class TokenBucket:
    """单桶令牌桶实现。"""

    def __init__(self, rate_per_minute: int, burst: int | None = None) -> None:
        self._rate = rate_per_minute / 60.0  # 每秒生成的令牌数
        self._burst = burst or rate_per_minute
        self._tokens = float(self._burst)
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> bool:
        """尝试获取一个令牌。返回 True 表示获取成功。"""
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_refill
            self._tokens = min(self._burst, self._tokens + elapsed * self._rate)
            self._last_refill = now

            if self._tokens >= 1.0:
                self._tokens -= 1.0
                return True
            return False


class ToolRateLimiter:
    """按工具名 + 全局两级的令牌桶速率限制器。"""

    def __init__(self, global_rate_per_minute: int = 100) -> None:
        self._global_bucket = TokenBucket(global_rate_per_minute)
        self._per_tool_buckets: dict[str, TokenBucket] = {}
        self._per_tool_rate = max(1, global_rate_per_minute // 2)  # 单工具默认限制为全局的一半，最少 1

    async def acquire(self, tool_name: str) -> bool:
        """尝试获取工具调用许可。先检查全局桶，再检查工具级桶。"""
        if not await self._global_bucket.acquire():
            logger.warning("全局工具调用速率限制触发")
            return False

        if tool_name not in self._per_tool_buckets:
            self._per_tool_buckets[tool_name] = TokenBucket(self._per_tool_rate)

        if not await self._per_tool_buckets[tool_name].acquire():
            logger.warning("工具 %s 调用速率限制触发", tool_name)
            return False

        return True

    async def throttled_call(self, tool_name: str, func, *args, **kwargs):
        """受速率限制的工具调用包装。"""
        if not await self.acquire(tool_name):
            return f"错误：工具 '{tool_name}' 调用过于频繁，请稍后重试。"
        return await func(*args, **kwargs)
