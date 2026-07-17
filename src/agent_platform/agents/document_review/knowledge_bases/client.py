"""外部知识库客户端。

调用万悟平台知识库命中（hit）接口执行检索，替代原本地 sqlite-vec 向量检索。
接口文档见 docs/知识库接口文档.md。
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import httpx

    from agent_platform.config.settings import Settings

logger = logging.getLogger(__name__)

_HIT_PATH = "/service/api/openapi/v1/knowledge/hit"


@dataclass
class KBHit:
    """知识库命中结果。"""

    kb_id: str  # 知识库标识（请求的知识库 id，见 _parse_hits）
    kb_file: str  # 命中来源文件名（取自响应 title）
    content: str  # 命中片段原文（取自响应 snippet）
    relevance: float  # 相关度得分（取自响应 score）


class KnowledgeHitClient:
    """万悟知识库 hit 接口客户端。

    检索参数（matchType / topK / threshold 等）由 settings 统一配置。
    """

    def __init__(self, http_client: "httpx.AsyncClient", settings: "Settings") -> None:
        self._http = http_client
        self._settings = settings

    @property
    def _url(self) -> str:
        return f"{self._settings.kb_api_base_url.rstrip('/')}{_HIT_PATH}"

    def _build_headers(self) -> dict:
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self._settings.kb_api_key:
            headers["Authorization"] = f"Bearer {self._settings.kb_api_key}"
        return headers

    def _build_payload(self, kb_ids: list[str], question: str) -> dict:
        s = self._settings
        return {
            "knowledgeList": [{"id": kb_id} for kb_id in kb_ids],
            "question": question,
            "knowledgeMatchParams": {
                "matchType": s.kb_match_type,
                "rerankModelId": s.kb_rerank_model_id,
                "priorityMatch": s.kb_priority_match,
                "semanticsPriority": s.kb_semantics_priority,
                "keywordPriority": s.kb_keyword_priority,
                "topK": s.kb_top_k,
                "threshold": s.kb_threshold,
                "useGraph": s.kb_use_graph,
            },
        }

    async def hit(self, kb_ids: list[str], question: str, retries: int = 1) -> list[KBHit]:
        """检索指定知识库，返回命中列表（按相关度降序）。

        重试策略：网络错误/3xx/5xx/畸形响应 重试 retries 次（带短退避）；
        4xx 与业务错误（code != 0，如无效知识库 ID）不可重试，直接抛出。

        Args:
            kb_ids: 知识库 ID 列表
            question: 待检索的问题/句子
            retries: 可重试错误的重试次数
        """
        payload = self._build_payload(kb_ids, question)
        headers = self._build_headers()

        last_error: Exception | None = None
        for attempt in range(retries + 1):
            if attempt > 0:
                await asyncio.sleep(0.5 * attempt)  # 短退避，避免瞬时故障期间立刻重试

            try:
                resp = await self._http.post(
                    self._url,
                    json=payload,
                    headers=headers,
                    timeout=self._settings.kb_request_timeout,
                )
            except Exception as e:  # 网络错误/超时 → 可重试
                last_error = e
                logger.warning("知识库检索请求失败（第 %d 次）: %s", attempt + 1, e)
                continue

            # 4xx 客户端错误（鉴权失败、参数非法等）→ 不可重试
            if 400 <= resp.status_code < 500:
                raise RuntimeError(f"知识库接口请求被拒绝: HTTP {resp.status_code} {resp.text[:200]}")
            # 3xx（重定向，通常是 base_url 配置问题）/ 5xx → 可重试，保留状态码便于排查
            if resp.status_code >= 300:
                last_error = RuntimeError(f"知识库接口异常响应: HTTP {resp.status_code}")
                logger.warning("知识库检索失败（第 %d 次）: %s", attempt + 1, last_error)
                continue

            try:
                data = resp.json()
            except Exception as e:  # 响应体畸形（如网关截断）→ 可重试
                last_error = e
                logger.warning("知识库响应解析失败（第 %d 次）: %s", attempt + 1, e)
                continue
            if not isinstance(data, dict):  # 合法 JSON 但非对象（如网关返回字符串）→ 可重试
                last_error = RuntimeError(f"知识库响应格式异常: {str(data)[:100]}")
                logger.warning("知识库响应格式异常（第 %d 次）: %s", attempt + 1, last_error)
                continue

            # 业务错误（如无效知识库 ID）→ 不可重试
            if data.get("code") != 0:
                raise RuntimeError(
                    f"知识库接口返回错误: code={data.get('code')} msg={data.get('msg')}"
                )
            return self._parse_hits(data.get("data") or {}, kb_ids)

        raise RuntimeError(f"知识库检索失败（已重试 {retries} 次）: {last_error}") from last_error

    @staticmethod
    def _parse_hits(data: dict, kb_ids: list[str]) -> list[KBHit]:
        """解析 hit 接口响应：zip(searchList, score) → KBHit 列表（按相关度降序）。

        kb_id 取请求的知识库 id：响应的 knowledgeName 若恰为请求 id 之一则直接对应；
        单库请求时命中必然来自该库；多库且无法对应时才回退到 knowledgeName。
        """
        search_list = data.get("searchList") or []
        scores = data.get("score") or []

        hits: list[KBHit] = []
        for i, item in enumerate(search_list):
            relevance = 0.0
            if i < len(scores):
                try:
                    relevance = round(float(scores[i]), 3)
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

        hits.sort(key=lambda h: h.relevance, reverse=True)
        return hits
