"""全局工具注册表 — declarative skills 通过工具名获取工具实例。"""

from __future__ import annotations

from langchain_core.tools import BaseTool

_registry: dict[str, BaseTool] = {}


def register(tool: BaseTool) -> None:
    _registry[tool.name] = tool


def register_all(tools: list[BaseTool]) -> None:
    for t in tools:
        register(t)


def get(name: str) -> BaseTool | None:
    return _registry.get(name)


def get_many(names: list[str]) -> list[BaseTool]:
    return [_registry[n] for n in names if n in _registry]


def tool_map() -> dict[str, BaseTool]:
    return dict(_registry)


def all_tools() -> list[BaseTool]:
    return list(_registry.values())
