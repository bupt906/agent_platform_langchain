from __future__ import annotations

import pytest

from agent_platform.config.settings import Settings
from agent_platform.models.provider import SUPPORTED_MODEL_PROVIDERS, ModelProvider


def test_supported_model_providers() -> None:
    assert SUPPORTED_MODEL_PROVIDERS == ("deepseek", "qwen", "ollama", "openai")


def test_describe_deepseek_model_uses_deepseek_endpoint(
    model_provider: ModelProvider,
    settings: Settings,
) -> None:
    info = model_provider.describe_model("deepseek:deepseek-v4-pro")

    assert info == {
        "model_id": "deepseek:deepseek-v4-pro",
        "provider": "deepseek",
        "provider_name": "DeepSeek",
        "model_name": "deepseek-v4-pro",
        "base_url": settings.models.deepseek_base_url,
        "api_mode": "openai-chat-completions",
    }


def test_model_identity_uses_authoritative_provider(
    model_provider: ModelProvider,
) -> None:
    instruction = model_provider.model_identity_instruction("deepseek:deepseek-v4-pro")

    assert "DeepSeek 提供的 deepseek-v4-pro" in instruction
    assert "权威运行时模型" in instruction


@pytest.mark.parametrize("model_id", ["deepseek-v4-pro", "unknown:model"])
def test_ambiguous_or_unknown_provider_is_rejected(
    model_provider: ModelProvider,
    model_id: str,
) -> None:
    with pytest.raises(ValueError):
        model_provider.get_model(model_id)
