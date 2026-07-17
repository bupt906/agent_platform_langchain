from __future__ import annotations

import logging

from langchain_core.language_models import BaseChatModel
from langchain_deepseek import ChatDeepSeek
from langchain_openai import ChatOpenAI

from agent_platform.config.settings import Settings

logger = logging.getLogger(__name__)


class ModelProvider:
    """统一的多模型路由，支持 DeepSeek / Qwen / Ollama / OpenAI 等 OpenAI 兼容接口。"""

    def __init__(self, settings: Settings, _cache: dict | None = None, _thinking: bool = False) -> None:
        self._settings = settings
        # 每个实例拥有独立的缓存，避免 with_thinking 副本污染原始缓存
        self._cache: dict[tuple[str, bool], BaseChatModel] = _cache if _cache is not None else {}
        self._thinking = _thinking

    @property
    def default_model(self) -> str:
        return self._settings.default_model

    @property
    def timeout(self) -> int:
        return self._settings.request_timeout

    @property
    def max_retries(self) -> int:
        return self._settings.max_retries

    def with_thinking(self, enabled: bool = True) -> ModelProvider:
        """返回共享缓存的请求级视图，不改变全局 provider 的默认行为。"""
        if enabled == self._thinking:
            return self

        return ModelProvider(self._settings, _cache=self._cache, _thinking=enabled)

    def get_model(self, model_id: str | None = None) -> BaseChatModel:
        model_id = model_id or self._settings.default_model
        cache_key = (model_id, self._thinking)
        if cache_key not in self._cache:
            self._cache[cache_key] = self._build_model(
                model_id,
                thinking=self._thinking,
            )
        return self._cache[cache_key]

    def _build_model(
        self,
        model_id: str,
        *,
        thinking: bool = False,
    ) -> BaseChatModel:
        opts = {
            "timeout": float(self.timeout),
            "max_retries": self.max_retries,
        }

        if ":" not in model_id:
            return ChatOpenAI(model=model_id, **opts)

        provider, model_name = model_id.split(":", 1)
        cfg = self._settings.models

        if provider == "deepseek":
            if thinking:
                return ChatDeepSeek(
                    model=model_name,
                    api_key=cfg.deepseek_api_key,
                    base_url=cfg.deepseek_base_url,
                    reasoning_effort="high",
                    extra_body={"thinking": {"type": "enabled"}},
                    **opts,
                )
            return ChatOpenAI(
                model=model_name,
                api_key=cfg.deepseek_api_key,
                base_url=cfg.deepseek_base_url,
                **opts,
            )
        if provider == "qwen":
            return ChatOpenAI(
                model=model_name,
                api_key=cfg.qwen_api_key,
                base_url=cfg.qwen_base_url,
                **opts,
            )
        if provider == "ollama":
            return ChatOpenAI(
                model=model_name,
                api_key="ollama",
                base_url=cfg.ollama_base_url,
                **opts,
            )
        if provider == "openai":
            return ChatOpenAI(
                model=model_name,
                api_key=cfg.openai_api_key,
                base_url=cfg.openai_base_url,
                **opts,
            )
        return ChatOpenAI(model=model_name, **opts)

    def get_fallback_model(self, model_ids: list[str] | None = None) -> BaseChatModel:
        """返回带 fallback 链的模型：主模型不可用时自动切换至备用模型。"""
        model_ids = model_ids or [self._settings.default_model, "openai:gpt-4o"]
        models = [self.get_model(mid) for mid in model_ids]
        return models[0].with_fallbacks(models[1:])

