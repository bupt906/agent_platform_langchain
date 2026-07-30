"""工具调用超时控制。

使用 asyncio.wait_for 为工具调用添加超时，超时后返回可读的错误信息让 Agent 自行恢复。
"""

from __future__ import annotations

import asyncio
import functools
import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)


def with_timeout(timeout_seconds: float = 30.0):
    """装饰器/包装器：为异步工具函数添加超时控制。

    用法：
        @with_timeout(10.0)
        async def my_tool(query: str) -> str: ...

    超时时返回错误消息字符串而非抛出异常，使 Agent 可以优雅处理。
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return await asyncio.wait_for(
                    func(*args, **kwargs), timeout=timeout_seconds
                )
            except asyncio.TimeoutError:
                tool_name = getattr(func, "name", func.__name__)
                logger.warning("工具 %s 执行超时 (%.1fs)", tool_name, timeout_seconds)
                return f"错误：工具 '{tool_name}' 执行超时（{timeout_seconds}秒）。请尝试缩小查询范围或简化操作后重试。"

        return wrapper

    return decorator


def wrap_tool_with_timeout(tool, timeout_seconds: float = 30.0):
    """为 LangChain Tool 对象包装超时控制。

    返回一个新的 tool，其 func/coroutine 被 asyncio.wait_for 包裹。
    """
    from langchain_core.tools import StructuredTool

    original_func = tool.func or tool.coroutine
    if original_func is None:
        return tool

    @functools.wraps(original_func)
    async def _wrapped(*args: Any, **kwargs: Any) -> Any:
        try:
            return await asyncio.wait_for(original_func(*args, **kwargs), timeout=timeout_seconds)
        except asyncio.TimeoutError:
            tool_name = getattr(tool, "name", "unknown")
            logger.warning("工具 %s 执行超时 (%.1fs)", tool_name, timeout_seconds)
            return f"错误：工具 '{tool_name}' 执行超时（{timeout_seconds}秒）。"

    return StructuredTool(
        name=tool.name,
        description=tool.description,
        func=None,
        coroutine=_wrapped,
        args_schema=tool.args_schema,
        return_direct=getattr(tool, "return_direct", False),
        response_format=getattr(tool, "response_format", "content"),
        metadata=getattr(tool, "metadata", None),
        tags=getattr(tool, "tags", None),
    )
