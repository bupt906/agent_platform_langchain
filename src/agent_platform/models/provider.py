from __future__ import annotations

from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI

from agent_platform.config.settings import Settings


class ModelProvider:
    """统一的多模型路由，支持 DeepSeek / Qwen / Ollama / OpenAI 等 OpenAI 兼容接口。"""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._cache: dict[str, BaseChatModel] = {}

    def get_model(self, model_id: str | None = None) -> BaseChatModel:
        model_id = model_id or self._settings.default_model
        if model_id not in self._cache:
            self._cache[model_id] = self._build_model(model_id)
        return self._cache[model_id]

    def _build_model(self, model_id: str) -> BaseChatModel:
        if ":" not in model_id:
            return ChatOpenAI(model=model_id)

        provider, model_name = model_id.split(":", 1)
        cfg = self._settings.models

        if provider == "deepseek":
            return ChatOpenAI(
                model=model_name,
                api_key=cfg.deepseek_api_key,
                base_url=cfg.deepseek_base_url,
            )
        if provider == "qwen":
            return ChatOpenAI(
                model=model_name,
                api_key=cfg.qwen_api_key,
                base_url=cfg.qwen_base_url,
            )
        if provider == "ollama":
            return ChatOpenAI(
                model=model_name,
                api_key="ollama",
                base_url=cfg.ollama_base_url,
            )
        if provider == "openai":
            return ChatOpenAI(
                model=model_name,
                api_key=cfg.openai_api_key,
                base_url=cfg.openai_base_url,
            )
        return ChatOpenAI(model=model_name)

    def get_fallback_model(
        self, model_ids: list[str] | None = None
    ) -> BaseChatModel:
        model_ids = model_ids or [self._settings.default_model, "openai:gpt-4o"]
        models = [self.get_model(mid) for mid in model_ids]
        return models[0].with_fallbacks(models[1:])
