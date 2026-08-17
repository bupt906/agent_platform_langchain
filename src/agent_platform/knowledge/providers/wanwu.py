"""万悟平台知识库后端。

调用万悟的 hit 接口执行检索。这是迁移前的既有实现，行为逐字保留，只是搬到了
:class:`~agent_platform.knowledge.provider.KnowledgeProvider` 接口后面，
好让调用方在切换到知识库中台时不需要改动。

接口约束以万悟服务端的 OpenAPI 和实现为准。
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from agent_platform.knowledge.models import KBHit, KBInfo, KBSearchResult
from agent_platform.knowledge.provider import (
    KnowledgeConfigError,
    KnowledgeProvider,
    KnowledgeUnavailable,
)

if TYPE_CHECKING:
    import httpx

    from agent_platform.config.settings import WanwuKnowledgeConfig

logger = logging.getLogger(__name__)

_HIT_PATH = "/service/api/openapi/v1/knowledge/hit"


class WanwuProvider(KnowledgeProvider):
    """万悟知识库 hit 接口客户端。

    检索参数（matchType / topK / threshold 等）由配置统一管理。
    """

    name = "wanwu"

    def __init__(self, http_client: "httpx.AsyncClient", config: "WanwuKnowledgeConfig") -> None:
        self._http = http_client
        self._config = config

    @property
    def _url(self) -> str:
        return f"{self._config.base_url.rstrip('/')}{_HIT_PATH}"

    def _build_headers(self) -> dict:
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self._config.api_key:
            headers["Authorization"] = f"Bearer {self._config.api_key}"
        return headers

    def _build_payload(self, kb_ids: list[str], question: str, top_k: int) -> dict:
        config = self._config
        return {
            "knowledgeList": [{"id": kb_id} for kb_id in kb_ids],
            "question": question,
            "knowledgeMatchParams": {
                "matchType": config.match_type,
                "rerankModelId": config.rerank_model_id,
                "priorityMatch": config.priority_match,
                "semanticsPriority": config.semantics_priority,
                "keywordPriority": config.keyword_priority,
                "topK": top_k,
                "threshold": config.threshold,
                "useGraph": config.use_graph,
            },
        }

    async def search(
        self,
        kb_ids: list[str],
        query: str,
        *,
        top_k: int | None = None,
    ) -> KBSearchResult:
        """检索指定知识库，返回命中列表（按相关度降序）。

        重试策略：网络错误 / 3xx / 5xx / 畸形响应重试 ``retries`` 次（带短退避）；
        4xx 与业务错误（code != 0，如无效知识库 ID）不可重试，直接抛出。
        """
        hits = await self._hit(kb_ids, query, top_k or self._config.top_k)
        # 万悟的 hit 接口不上报后端降级信息，因此 degraded 恒为空。
        return KBSearchResult(hits=hits, degraded=[])

    async def _hit(self, kb_ids: list[str], question: str, top_k: int) -> list[KBHit]:
        payload = self._build_payload(kb_ids, question, top_k)
        headers = self._build_headers()
        retries = self._config.retries

        last_error: Exception | None = None
        for attempt in range(retries + 1):
            if attempt > 0:
                await asyncio.sleep(0.5 * attempt)  # 短退避，避免瞬时故障期间立刻重试

            try:
                resp = await self._http.post(
                    self._url,
                    json=payload,
                    headers=headers,
                    timeout=self._config.request_timeout,
                )
            except Exception as exc:  # 网络错误/超时 → 可重试
                last_error = exc
                logger.warning(
                    "知识库检索请求失败（第 %d 次）: [%s] %s | url=%s",
                    attempt + 1, type(exc).__name__, exc, self._url,
                )
                continue

            # 4xx 客户端错误（鉴权失败、参数非法等）→ 不可重试
            if 400 <= resp.status_code < 500:
                raise KnowledgeConfigError(
                    f"知识库接口请求被拒绝: HTTP {resp.status_code} {resp.text[:200]}"
                )
            # 3xx（重定向，通常是 base_url 配置问题）/ 5xx → 可重试，保留状态码便于排查
            if resp.status_code >= 300:
                last_error = RuntimeError(f"知识库接口异常响应: HTTP {resp.status_code}")
                logger.warning("知识库检索失败（第 %d 次）: %s", attempt + 1, last_error)
                continue

            try:
                data = resp.json()
            except Exception as exc:  # 响应体畸形（如网关截断）→ 可重试
                last_error = exc
                logger.warning("知识库响应解析失败（第 %d 次）: %s", attempt + 1, exc)
                continue
            if not isinstance(data, dict):  # 合法 JSON 但非对象（如网关返回字符串）→ 可重试
                last_error = RuntimeError(f"知识库响应格式异常: {str(data)[:100]}")
                logger.warning("知识库响应格式异常（第 %d 次）: %s", attempt + 1, last_error)
                continue

            # 业务错误（如无效知识库 ID）→ 不可重试
            if data.get("code") != 0:
                raise KnowledgeConfigError(
                    f"知识库接口返回错误: code={data.get('code')} msg={data.get('msg')}"
                )
            return self._parse_hits(data.get("data") or {}, kb_ids)

        raise KnowledgeUnavailable(
            f"知识库检索失败（已重试 {retries} 次）: {last_error}"
        ) from last_error

    async def list_kbs(self) -> list[KBInfo]:
        """万悟的 hit 接口不提供知识库清单，知识库 ID 由调用方传入。"""
        return []

    async def health(self) -> dict:
        return {"provider": self.name, "status": "unknown", "base_url": self._config.base_url}

    @staticmethod
    def _parse_hits(data: dict, kb_ids: list[str]) -> list[KBHit]:
        """解析 hit 接口响应：zip(searchList, score) → KBHit 列表（按相关度降序）。

        kb_id 取请求的知识库 id：响应的 knowledgeName 若恰为请求 id 之一则直接对应；
        单库请求时命中必然来自该库；多库且无法对应时才回退到 knowledgeName。
        """
        search_list = data.get("searchList") or []
        scores = data.get("score") or []

        hits: list[KBHit] = []
        for index, item in enumerate(search_list):
            relevance = 0.0
            if index < len(scores):
                try:
                    relevance = round(float(scores[index]), 3)
                except (TypeError, ValueError):
                    relevance = 0.0

            # kb_id 取请求的知识库 id：单库请求命中必然来自该库；
            # 多库时响应的 knowledgeName 若恰为请求 id 之一则天然对应，否则只能原样保留
            knowledge_name = str(item.get("knowledgeName", ""))
            kb_id = kb_ids[0] if len(kb_ids) == 1 else knowledge_name

            hits.append(
                KBHit(
                    kb_id=kb_id,
                    kb_file=item.get("title", ""),
                    content=item.get("snippet", ""),
                    relevance=relevance,
                )
            )

        hits.sort(key=lambda hit: hit.relevance, reverse=True)
        return hits
