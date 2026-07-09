from __future__ import annotations

import asyncio
import logging
from typing import overload

from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI
from openai import AsyncOpenAI

from agent_platform.config.settings import Settings

logger = logging.getLogger(__name__)


class ModelProvider:
    """统一的多模型路由，支持 DeepSeek / Qwen / Ollama / OpenAI 等 OpenAI 兼容接口。"""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._cache: dict[str, BaseChatModel] = {}

    @property
    def timeout(self) -> int:
        return self._settings.request_timeout

    @property
    def max_retries(self) -> int:
        return self._settings.max_retries

    def get_model(self, model_id: str | None = None) -> BaseChatModel:
        model_id = model_id or self._settings.default_model
        if model_id not in self._cache:
            self._cache[model_id] = self._build_model(model_id)
        return self._cache[model_id]

    def _build_model(self, model_id: str) -> BaseChatModel:
        opts = {
            "timeout": float(self.timeout),
            "max_retries": self.max_retries,
        }

        if ":" not in model_id:
            return ChatOpenAI(model=model_id, **opts)

        provider, model_name = model_id.split(":", 1)
        cfg = self._settings.models

        if provider == "deepseek":
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

    def get_fallback_model(
        self, model_ids: list[str] | None = None
    ) -> BaseChatModel:
        """返回带 fallback 链的模型：主模型不可用时自动切换至备用模型。"""
        model_ids = model_ids or [self._settings.default_model, "openai:gpt-4o"]
        models = [self.get_model(mid) for mid in model_ids]
        return models[0].with_fallbacks(models[1:])

    # ── Embedding ───────────────────────────────────────────

    @property
    def embedding_supported(self) -> bool:
        """检查当前配置是否支持 embedding。DeepSeek 不支持 /v1/embeddings。"""
        model_id = self._settings.embedding_model or self._settings.default_model
        if ":" in model_id:
            provider = model_id.split(":", 1)[0]
        else:
            provider = "openai"
        # DeepSeek 不支持 embedding API，Ollama 需要手动配置模型
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

        if provider == "deepseek":
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
