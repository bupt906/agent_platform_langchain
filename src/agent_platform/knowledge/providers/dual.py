"""迁移期的双跑比对后端。

同一个查询同时发给主后端和影子后端，**只返回主后端的结果**，把两边的差异写进日志。
用途是在真实流量上量化「换后端会让审阅结论变成什么样」，而不是靠上线后再观察。

影子后端的任何失败都不会影响调用方——它只是观测手段，不是依赖。
"""

from __future__ import annotations

import asyncio
import logging

from agent_platform.knowledge.models import (
    KBAnswer,
    KBDocument,
    KBInfo,
    KBIngestResult,
    KBSearchResult,
)
from agent_platform.knowledge.provider import KnowledgeProvider

logger = logging.getLogger(__name__)


class DualProvider(KnowledgeProvider):
    """主后端 + 影子后端的比对包装。"""

    name = "dual"

    def __init__(self, primary: KnowledgeProvider, shadow: KnowledgeProvider) -> None:
        self._primary = primary
        self._shadow = shadow

    async def search(
        self,
        kb_ids: list[str],
        query: str,
        *,
        top_k: int | None = None,
    ) -> KBSearchResult:
        primary_task = asyncio.create_task(self._primary.search(kb_ids, query, top_k=top_k))
        shadow_task = asyncio.create_task(self._shadow.search(kb_ids, query, top_k=top_k))
        primary, shadow = await asyncio.gather(
            primary_task, shadow_task, return_exceptions=True
        )

        if isinstance(primary, BaseException):
            # 主后端失败就是失败，不能拿影子结果顶替——那会掩盖迁移目标的真实可用性。
            raise primary

        self._log_difference(query, primary, shadow)
        return primary

    def _log_difference(
        self, query: str, primary: KBSearchResult, shadow: KBSearchResult | BaseException
    ) -> None:
        if isinstance(shadow, BaseException):
            logger.info(
                "知识库双跑 | query=%.40s | 主(%s)=%d 条 | 影子(%s)失败: %s",
                query, self._primary.name, len(primary.hits), self._shadow.name, shadow,
            )
            return

        primary_files = {hit.kb_file for hit in primary.hits}
        shadow_files = {hit.kb_file for hit in shadow.hits}
        overlap = primary_files & shadow_files
        union = primary_files | shadow_files
        logger.info(
            "知识库双跑 | query=%.40s | 主(%s)=%d 条/%d 文件 | 影子(%s)=%d 条/%d 文件 "
            "| 文件重合=%d/%d | 主降级=%s",
            query,
            self._primary.name, len(primary.hits), len(primary_files),
            self._shadow.name, len(shadow.hits), len(shadow_files),
            len(overlap), len(union) or 0,
            primary.degraded or "无",
        )

    async def answer(
        self,
        question: str,
        kb_ids: list[str],
        *,
        top_k: int | None = None,
    ) -> KBAnswer:
        return await self._primary.answer(question, kb_ids, top_k=top_k)

    async def list_kbs(self) -> list[KBInfo]:
        return await self._primary.list_kbs()

    async def fetch_document(self, doc_id: str) -> KBDocument:
        return await self._primary.fetch_document(doc_id)

    async def ingest_document(
        self,
        kb_id: str,
        filename: str,
        content: bytes,
        *,
        content_type: str = "application/octet-stream",
    ) -> KBIngestResult:
        # 写入只发给主后端。影子后端是观测手段，不该产生副作用。
        return await self._primary.ingest_document(
            kb_id, filename, content, content_type=content_type
        )

    async def health(self) -> dict:
        primary, shadow = await asyncio.gather(
            self._primary.health(), self._shadow.health(), return_exceptions=True
        )
        return {
            "provider": self.name,
            "primary": primary if not isinstance(primary, BaseException) else str(primary),
            "shadow": shadow if not isinstance(shadow, BaseException) else str(shadow),
        }
