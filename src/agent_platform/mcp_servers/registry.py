"""MCP Server 集成 — 使用 langchain-mcp-adapters 将 MCP 工具转为 LangChain 工具。"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def load_mcp_config(config_path: Path) -> list[dict[str, Any]]:
    """读取 mcp_config.json，返回已启用的 MCP 服务器配置列表。"""
    if not config_path.exists():
        logger.warning("MCP 配置文件不存在: %s", config_path)
        return []

    data = json.loads(config_path.read_text())
    servers = data.get("mcpServers", {})
    enabled = []

    for name, cfg in servers.items():
        if not cfg.get("enabled", True):
            continue
        enabled.append({"name": name, **cfg})

    return enabled


async def load_mcp_tools(config_path: Path) -> list:
    """从配置中加载所有已启用 MCP 服务器的工具。

    使用 langchain-mcp-adapters 的 MultiServerMCPClient 将 MCP 工具
    转换为 LangChain BaseTool 实例。

    返回 LangChain 工具列表。如果 langchain-mcp-adapters 未安装则返回空列表。
    """
    configs = load_mcp_config(config_path)
    if not configs:
        return []

    try:
        from langchain_mcp_adapters.client import MultiServerMCPClient
    except ImportError:
        logger.warning(
            "langchain-mcp-adapters 未安装，跳过 MCP 工具加载。"
            "请运行: pip install langchain-mcp-adapters"
        )
        return []

    server_params: dict[str, dict] = {}
    for cfg in configs:
        name = cfg["name"]
        if "command" in cfg:
            server_params[name] = {
                "command": cfg["command"],
                "args": cfg.get("args", []),
                "transport": "stdio",
            }
        elif "url" in cfg:
            server_params[name] = {
                "url": cfg["url"],
                "transport": "streamable_http",
            }

    if not server_params:
        return []

    tools = []
    async with MultiServerMCPClient(server_params) as client:
        tools = client.get_tools()
        logger.info("从 MCP 服务器加载了 %d 个工具", len(tools))

    return tools


# ── 缓存（动态重载用） ─────────────────────────────────────

_mcp_tool_cache: dict[str, tuple[float, list]] = {}


async def load_mcp_tools_dynamic(
    config_path: Path,
    *,
    tool_filter: str | None = None,
    cache_ttl: float = 300.0,
) -> list:
    """动态加载 MCP 工具，支持缓存和筛选。

    与 load_mcp_tools 类似，但：
    - 按 config_path 缓存结果，TTL 后自动重新加载
    - 支持 tool_filter 按名称筛选工具
    - 适合运行时动态添加/移除 MCP 工具

    Args:
        config_path: MCP 配置文件路径
        tool_filter: 可选，工具名前缀筛选
        cache_ttl: 缓存有效期（秒），0 = 不缓存

    Returns:
        LangChain 工具列表
    """
    import time

    cache_key = str(config_path.absolute())
    now = time.monotonic()

    if cache_ttl > 0 and cache_key in _mcp_tool_cache:
        cached_at, cached_tools = _mcp_tool_cache[cache_key]
        if now - cached_at < cache_ttl:
            tools = cached_tools
            if tool_filter:
                tools = [t for t in tools if t.name.startswith(tool_filter)]
            return tools

    tools = await load_mcp_tools(config_path)
    _mcp_tool_cache[cache_key] = (now, tools)

    if tool_filter:
        tools = [t for t in tools if t.name.startswith(tool_filter)]

    return tools


def invalidate_mcp_cache(config_path: Path | None = None) -> None:
    """使 MCP 工具缓存失效。如果不传 config_path 则清空全部缓存。"""
    if config_path:
        _mcp_tool_cache.pop(str(config_path.absolute()), None)
    else:
        _mcp_tool_cache.clear()
