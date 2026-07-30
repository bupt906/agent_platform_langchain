from __future__ import annotations

import logging

from langchain_core.language_models import BaseChatModel
from langchain_deepseek import ChatDeepSeek
from langchain_openai import ChatOpenAI

from agent_platform.config.settings import Settings

logger = logging.getLogger(__name__)

SUPPORTED_MODEL_PROVIDERS = ("volcengine", "deepseek", "qwen", "ollama", "openai")
PROVIDER_DISPLAY_NAMES = {
    "volcengine": "火山引擎方舟",
    "deepseek": "DeepSeek",
    "qwen": "通义千问",
    "ollama": "Ollama",
    "openai": "OpenAI",
}


class ModelProvider:
    """统一的多模型路由，支持火山引擎 / DeepSeek / Qwen / Ollama / OpenAI。"""

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

    def describe_model(self, model_id: str | None = None) -> dict[str, str]:
        """解析模型 ID，返回不含密钥的权威连接信息。"""
        resolved_id = model_id or self._settings.default_model
        if ":" not in resolved_id:
            raise ValueError(
                f"模型 ID '{resolved_id}' 缺少 provider 前缀；请使用 provider:model 格式，例如 deepseek:deepseek-v4-pro"
            )

        provider, model_name = resolved_id.split(":", 1)
        if provider not in SUPPORTED_MODEL_PROVIDERS:
            supported = ", ".join(SUPPORTED_MODEL_PROVIDERS)
            raise ValueError(f"不支持的模型 provider '{provider}'；可用值: {supported}")
        if not model_name:
            raise ValueError(f"模型 ID '{resolved_id}' 缺少模型名称")

        cfg = self._settings.models
        base_urls = {
            "volcengine": cfg.volcengine_base_url,
            "deepseek": cfg.deepseek_base_url,
            "qwen": cfg.qwen_base_url,
            "ollama": cfg.ollama_base_url,
            "openai": cfg.openai_base_url,
        }
        return {
            "model_id": resolved_id,
            "provider": provider,
            "provider_name": PROVIDER_DISPLAY_NAMES[provider],
            "model_name": model_name,
            "base_url": base_urls[provider],
            "api_mode": ("openai-responses" if provider == "volcengine" else "openai-chat-completions"),
        }

    def model_identity_instruction(self, model_id: str | None = None) -> str:
        """生成供系统提示词使用的模型身份说明，避免模型自行猜测。"""
        info = self.describe_model(model_id)
        if info["provider"] == "volcengine" and info["model_name"] == "ark-code-latest":
            identity = (
                "本次请求通过火山引擎方舟 Coding 网关的 ark-code-latest 路由；"
                "底层模型由方舟配置决定，服务端未报告时不得猜测具体模型。"
            )
        else:
            identity = f"本次请求的权威运行时模型是 {info['provider_name']} 提供的 {info['model_name']}。"
        return (
            f"{identity} 如果用户询问模型身份，必须依据此运行时信息回答，"
            "不要根据训练语料、客户端名称或兼容协议猜测其他供应商。"
        )

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

        info = self.describe_model(model_id)
        provider = info["provider"]
        model_name = info["model_name"]
        cfg = self._settings.models

        if provider == "volcengine":
            return ChatOpenAI(
                model=model_name,
                api_key=cfg.volcengine_api_key,
                base_url=cfg.volcengine_base_url,
                use_responses_api=True,
                **opts,
            )
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
        raise AssertionError(f"未处理的模型 provider: {provider}")

    def get_fallback_model(self, model_ids: list[str] | None = None) -> BaseChatModel:
        """返回带 fallback 链的模型：主模型不可用时自动切换至备用模型。"""
        model_ids = model_ids or [self._settings.default_model, "openai:gpt-4o"]
        models = [self.get_model(mid) for mid in model_ids]
        return models[0].with_fallbacks(models[1:])
