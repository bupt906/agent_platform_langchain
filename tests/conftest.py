from __future__ import annotations

import httpx
import pytest
from langgraph.checkpoint.memory import InMemorySaver

from agent_platform.config.settings import Settings
from agent_platform.core.deps import PlatformDeps
from agent_platform.core.registry import SkillRegistry
from agent_platform.models.provider import ModelProvider


@pytest.fixture
def settings() -> Settings:
    """返回测试用配置，使用 mock key 避免意外触发网络请求。"""
    s = Settings(
        default_model="deepseek:deepseek-chat",
        deepseek_api_key="test-key",
        openai_api_key="test-key",
    )
    # 用 mock key 覆盖 ModelConfig 的默认 env 读取
    s.models.deepseek_api_key = "test-key"
    s.models.openai_api_key = "test-key"
    s.models.qwen_api_key = "test-key"
    return s


@pytest.fixture
def model_provider(settings: Settings) -> ModelProvider:
    return ModelProvider(settings)


@pytest.fixture
def skill_registry() -> SkillRegistry:
    registry = SkillRegistry()
    registry.auto_discover()
    return registry


@pytest.fixture
def checkpointer() -> InMemorySaver:
    return InMemorySaver()


@pytest.fixture
async def deps(
    model_provider: ModelProvider, skill_registry: SkillRegistry
) -> PlatformDeps:
    async with httpx.AsyncClient(proxy=None) as client:
        yield PlatformDeps(
            model_provider=model_provider,
            skill_registry=skill_registry,
            http_client=client,
            checkpointer=InMemorySaver(),
        )
