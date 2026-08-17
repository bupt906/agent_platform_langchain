"""知识库能力。

平台的知识库检索统一走 :class:`KnowledgeProvider` 接口，具体后端由
:func:`build_provider` 按配置构造。要接一个新后端，实现接口并在 factory 里加一个
分支即可，调用方无需改动。

对 Agent 和 Skill 而言，更常用的入口是注册在全局工具表里的 ``search_knowledge`` 等
工具（见 :mod:`agent_platform.tools.knowledge_tools`），不必直接持有 provider。
"""

from agent_platform.knowledge.factory import DUAL, OMNIMIND, WANWU, build_provider
from agent_platform.knowledge.models import (
    KBAnswer,
    KBDocument,
    KBHit,
    KBInfo,
    KBIngestResult,
    KBSearchResult,
)
from agent_platform.knowledge.provider import (
    KnowledgeConfigError,
    KnowledgeError,
    KnowledgeProvider,
    KnowledgeUnavailable,
)

__all__ = [
    "DUAL",
    "OMNIMIND",
    "WANWU",
    "KBAnswer",
    "KBDocument",
    "KBHit",
    "KBIngestResult",
    "KBInfo",
    "KBSearchResult",
    "KnowledgeConfigError",
    "KnowledgeError",
    "KnowledgeProvider",
    "KnowledgeUnavailable",
    "build_provider",
]
