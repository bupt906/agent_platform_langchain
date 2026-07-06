from __future__ import annotations

from dataclasses import dataclass, field

import httpx
from langgraph.checkpoint.memory import InMemorySaver

from agent_platform.core.registry import SkillRegistry
from agent_platform.models.provider import ModelProvider


@dataclass
class PlatformDeps:
    """全局依赖容器，在 FastAPI lifespan 中初始化。"""

    model_provider: ModelProvider
    skill_registry: SkillRegistry
    http_client: httpx.AsyncClient
    checkpointer: InMemorySaver = field(default_factory=InMemorySaver)
