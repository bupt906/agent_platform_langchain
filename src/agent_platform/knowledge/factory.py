"""按配置构造知识库后端。

这是整个迁移的开关所在：``settings.knowledge_provider`` 决定用哪个实现，其余代码
——Agent、Skill、工具层、审阅流水线——只认 :class:`KnowledgeProvider` 接口，
因此切换后端不需要改动它们中的任何一处。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from agent_platform.knowledge.provider import KnowledgeConfigError, KnowledgeProvider

if TYPE_CHECKING:
    import httpx

    from agent_platform.config.settings import Settings

logger = logging.getLogger(__name__)

WANWU = "wanwu"
OMNIMIND = "omnimind"
DUAL = "dual"


def build_provider(http_client: "httpx.AsyncClient", settings: "Settings") -> KnowledgeProvider:
    """根据 ``settings.knowledge_provider`` 构造后端实例。"""
    choice = (settings.knowledge_provider or WANWU).strip().lower()

    if choice == WANWU:
        from agent_platform.knowledge.providers.wanwu import WanwuProvider

        logger.info("知识库后端: 万悟平台 (%s)", settings.wanwu.base_url)
        return WanwuProvider(http_client, settings.wanwu)

    if choice == OMNIMIND:
        from agent_platform.knowledge.providers.omnimind import OmniMindProvider

        logger.info("知识库后端: 知识库中台 (%s)", settings.omnimind.base_url)
        return OmniMindProvider(http_client, settings.omnimind)

    if choice == DUAL:
        from agent_platform.knowledge.providers.dual import DualProvider
        from agent_platform.knowledge.providers.omnimind import OmniMindProvider
        from agent_platform.knowledge.providers.wanwu import WanwuProvider

        logger.info(
            "知识库后端: 双跑比对模式，主 = 知识库中台 (%s)，影子 = 万悟平台 (%s)",
            settings.omnimind.base_url,
            settings.wanwu.base_url,
        )
        return DualProvider(
            primary=OmniMindProvider(http_client, settings.omnimind),
            shadow=WanwuProvider(http_client, settings.wanwu),
        )

    raise KnowledgeConfigError(
        f"未知的知识库后端 {choice!r}；可选值: {WANWU} / {OMNIMIND} / {DUAL}"
    )
