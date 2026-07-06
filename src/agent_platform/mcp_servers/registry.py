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
