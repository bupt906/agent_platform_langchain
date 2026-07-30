from __future__ import annotations

import asyncio
import logging
from copy import copy

from langchain_core.language_models import BaseChatModel
from langchain_deepseek import ChatDeepSeek
from langchain_openai import ChatOpenAI
from openai import AsyncOpenAI

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

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._cache: dict[tuple[str, bool], BaseChatModel] = {}
        self._thinking = False

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

        provider = copy(self)
        provider._thinking = enabled
        return provider

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

    # ── Embedding ───────────────────────────────────────────

    @property
    def embedding_supported(self) -> bool:
        """检查当前配置是否支持 embedding。"""
        model_id = self._settings.embedding_model or self._settings.default_model
        if ":" in model_id:
            provider = model_id.split(":", 1)[0]
        else:
            provider = "openai"
        # 编码模型不直接用于 embedding；仅在显式配置 embedding 模型时尝试。
        if provider == "volcengine":
            return self._settings.embedding_model != ""
        if provider == "deepseek":
            return self._settings.embedding_model != ""  # 只有显式配置了 embedding_model 才尝试
        return True

    def _get_embedding_client(self) -> AsyncOpenAI | None:
        """根据配置返回 OpenAI 兼容的 embedding 客户端。不支持 embedding 的 provider 返回 None。"""
        cfg = self._settings.models

        # 显式配置的 embedding_model 优先
        explicit = self._settings.embedding_model
        if explicit and ":" in explicit:
            provider = explicit.split(":", 1)[0]
        else:
            model_id = self._settings.default_model
            provider = model_id.split(":", 1)[0] if ":" in model_id else "openai"

        if provider == "volcengine":
            if not explicit:
                return None
            return AsyncOpenAI(api_key=cfg.volcengine_api_key, base_url=cfg.volcengine_base_url)
        elif provider == "deepseek":
            # DeepSeek 不支持 embeddings，除非用户显式指定了 embedding_model
            if not explicit:
                return None
            return AsyncOpenAI(api_key=cfg.deepseek_api_key, base_url=cfg.deepseek_base_url)
        elif provider == "qwen":
            return AsyncOpenAI(api_key=cfg.qwen_api_key, base_url=cfg.qwen_base_url)
        elif provider == "ollama":
            return AsyncOpenAI(api_key="ollama", base_url=cfg.ollama_base_url)
        else:
            return AsyncOpenAI(api_key=cfg.openai_api_key, base_url=cfg.openai_base_url)

    @property
    def embedding_model_name(self) -> str:
        """获取实际使用的 embedding 模型名。"""
        explicit = self._settings.embedding_model
        if explicit:
            return explicit.split(":", 1)[1] if ":" in explicit else explicit
        # 返回 OpenAI 兼容的默认 embedding 模型
        return "text-embedding-3-small"

    async def embed(self, text: str) -> list[float]:
        """对单个文本生成 embedding 向量。

        如果当前 provider 不支持 embedding，返回零向量（调用方应回退到关键词检索）。
        """
        client = self._get_embedding_client()
        if client is None:
            return [0.0] * self._settings.embedding_dimensions

        model = self.embedding_model_name
        try:
            resp = await client.embeddings.create(model=model, input=text)
            return resp.data[0].embedding
        except Exception as e:
            logger.warning("Embedding 请求失败 (%s): %s，回退到零向量", model, e)
            return [0.0] * self._settings.embedding_dimensions

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """批量生成 embedding 向量，自动分批控制并发。

        如果 provider 不支持 embedding，返回零向量列表。
        """
        if not texts:
            return []

        client = self._get_embedding_client()
        if client is None:
            return [[0.0] * self._settings.embedding_dimensions for _ in texts]

        batch_size = 10
        results: list[list[float]] = [None] * len(texts)  # type: ignore[list-item]

        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            tasks = [self.embed(t) for t in batch]
            vecs = await asyncio.gather(*tasks)
            for j, v in enumerate(vecs):
                results[i + j] = v  # type: ignore[index]

        return results  # type: ignore[return-value]
