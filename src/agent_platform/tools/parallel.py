"""并行工具执行支持。

当 Agent 在单个 ReAct 步骤中发出多个工具调用时，利用 asyncio.gather 并行执行。
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)


async def execute_tools_parallel(
    calls: list[tuple[str, Any, tuple, dict]],
    max_concurrency: int = 5,
) -> list[tuple[str, Any]]:
    """并行执行多个工具调用。

    Args:
        calls: [(tool_name, callable, args, kwargs), ...] 列表
        max_concurrency: 最大并发数

    Returns:
        [(tool_name, result), ...] 与输入顺序一致的结果列表
    """
    semaphore = asyncio.Semaphore(max_concurrency)

    async def _run_one(name: str, func: Any, args: tuple, kwargs: dict) -> tuple[str, Any]:
        async with semaphore:
            try:
                result = await func(*args, **kwargs)
                return name, result
            except Exception as e:
                logger.warning("并行工具执行失败 [%s]: %s", name, e)
                return name, f"错误：工具 '{name}' 执行失败: {e}"

    tasks = [_run_one(name, func, args, kwargs) for name, func, args, kwargs in calls]
    results = await asyncio.gather(*tasks)
    return list(results)


async def make_parallel_callable(tools: list, max_concurrency: int = 5):
    """返回一个统一入口，当传入多个调用时并行执行。

    这是一个适配层，将工具调用接口统一为异步并行执行。
    """
    semaphore = asyncio.Semaphore(max_concurrency)

    async def _call_tool(tool, *args, **kwargs):
        async with semaphore:
            func = tool.coroutine or tool.func
            if func is None:
                return f"错误：工具 '{tool.name}' 无可调用函数"
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                return f"错误：工具 '{tool.name}' 执行失败: {e}"

    return _call_tool
