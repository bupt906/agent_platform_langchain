from __future__ import annotations

import httpx
import pytest

from agent_platform.config.settings import Settings
from agent_platform.core.deps import PlatformDeps
from agent_platform.core.registry import SkillRegistry
from agent_platform.models.provider import ModelProvider


@pytest.fixture
def settings() -> Settings:
    return Settings(default_model="deepseek:deepseek-chat")


@pytest.fixture
def model_provider(settings: Settings) -> ModelProvider:
    return ModelProvider(settings)


@pytest.fixture
def skill_registry() -> SkillRegistry:
    registry = SkillRegistry()
    registry.auto_discover()
    return registry


@pytest.fixture
async def deps(
    model_provider: ModelProvider, skill_registry: SkillRegistry
) -> PlatformDeps:
    async with httpx.AsyncClient() as client:
        yield PlatformDeps(
            model_provider=model_provider,
            skill_registry=skill_registry,
            http_client=client,
        )
