"""知识库中台（万象智库 OmniMind）后端。

走中台的 ``/api/v1/service`` 契约层，传输、重试与契约版本校验由 ``kb_sdk`` 负责，
这里只做两件事：领域模型翻译，和知识库 ID 的迁移期映射。
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from agent_platform.knowledge.models import (
    KBAnswer,
    KBDocument,
    KBHit,
    KBInfo,
    KBIngestResult,
    KBSearchResult,
)
from agent_platform.knowledge.provider import (
    KnowledgeConfigError,
    KnowledgeProvider,
    KnowledgeUnavailable,
)

if TYPE_CHECKING:
    import httpx

    from agent_platform.config.settings import OmniMindKnowledgeConfig

logger = logging.getLogger(__name__)

_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)


def parse_kb_id_map(raw: str) -> dict[str, str]:
    """解析 ``"旧id:新id,旧id2:新id2"`` 形式的映射配置。"""
    mapping: dict[str, str] = {}
    for entry in (raw or "").split(","):
        entry = entry.strip()
        if not entry:
            continue
        old, sep, new = entry.partition(":")
        if not sep or not old.strip() or not new.strip():
            raise KnowledgeConfigError(
                f"OMNIMIND_KB_ID_MAP 条目格式应为 '旧id:新id'，收到 {entry!r}"
            )
        mapping[old.strip()] = new.strip()
    return mapping


class OmniMindProvider(KnowledgeProvider):
    """知识库中台服务契约层客户端。"""

    name = "omnimind"

    def __init__(self, http_client: "httpx.AsyncClient", config: "OmniMindKnowledgeConfig") -> None:
        from kb_sdk import KnowledgeServiceClient

        self._config = config
        self._kb_id_map = parse_kb_id_map(config.kb_id_map)
        self._client = KnowledgeServiceClient(
            config.base_url,
            config.api_key,
            http_client=http_client,
            timeout=config.request_timeout,
            retries=config.retries,
        )

    # ── 知识库 ID 迁移映射 ────────────────────────────────

    def _map_kb_ids(self, kb_ids: list[str]) -> list[str]:
        """把调用方传入的知识库 ID 翻译成中台的 UUID。

        外部系统（例如审阅任务的下发方）仍在用万悟的数字串 ID。映射表让它们不必与本次
        迁移同步改造。遇到查无对应的旧格式 ID 时直接报错，而不是原样发出去——那样只会
        换来一个语焉不详的 403。
        """
        if not kb_ids:
            return []
        mapped: list[str] = []
        for kb_id in kb_ids:
            target = self._kb_id_map.get(kb_id)
            if target:
                logger.debug("知识库 ID 映射: %s -> %s", kb_id, target)
                mapped.append(target)
                continue
            if not _UUID_RE.match(kb_id):
                raise KnowledgeConfigError(
                    f"知识库 ID {kb_id!r} 不是知识库中台的 UUID，且未配置映射。"
                    f"请在 OMNIMIND_KB_ID_MAP 中补充 '{kb_id}:<中台知识库UUID>'。"
                )
            mapped.append(kb_id)
        return mapped

    # ── 契约方法 ──────────────────────────────────────────

    async def search(
        self,
        kb_ids: list[str],
        query: str,
        *,
        top_k: int | None = None,
    ) -> KBSearchResult:
        from kb_sdk import KnowledgeAuthError, KnowledgeRequestError, KnowledgeServiceError

        scope = self._map_kb_ids(kb_ids)
        try:
            result = await self._client.search(
                query,
                kb_ids=scope or None,
                top_k=top_k or self._config.top_k,
            )
        except (KnowledgeAuthError, KnowledgeRequestError) as exc:
            raise KnowledgeConfigError(str(exc)) from exc
        except KnowledgeServiceError as exc:
            raise KnowledgeUnavailable(str(exc)) from exc

        return KBSearchResult(
            hits=[_as_kb_hit(hit) for hit in result.hits],
            degraded=list(result.degraded),
            took_ms=result.took_ms,
        )

    async def answer(
        self,
        question: str,
        kb_ids: list[str],
        *,
        top_k: int | None = None,
    ) -> KBAnswer:
        from kb_sdk import KnowledgeAuthError, KnowledgeRequestError, KnowledgeServiceError

        scope = self._map_kb_ids(kb_ids)
        try:
            result = await self._client.answer(
                question,
                kb_ids=scope or None,
                top_k=top_k or self._config.top_k,
            )
        except (KnowledgeAuthError, KnowledgeRequestError) as exc:
            raise KnowledgeConfigError(str(exc)) from exc
        except KnowledgeServiceError as exc:
            raise KnowledgeUnavailable(str(exc)) from exc

        return KBAnswer(
            answer=result.answer,
            citations=[_as_kb_hit(hit) for hit in result.citations],
            model=result.model,
            provider=result.provider,
            degraded=list(result.degraded),
            grounded=result.grounded,
        )

    async def list_kbs(self) -> list[KBInfo]:
        from kb_sdk import KnowledgeAuthError, KnowledgeServiceError

        try:
            items = await self._client.list_kbs()
        except KnowledgeAuthError as exc:
            raise KnowledgeConfigError(str(exc)) from exc
        except KnowledgeServiceError as exc:
            raise KnowledgeUnavailable(str(exc)) from exc
        return [
            KBInfo(
                kb_id=item.kb_id,
                name=item.name,
                description=item.description,
                document_count=item.document_count,
            )
            for item in items
        ]

    async def fetch_document(self, doc_id: str) -> KBDocument:
        from kb_sdk import KnowledgeAuthError, KnowledgeRequestError, KnowledgeServiceError

        try:
            doc = await self._client.document(doc_id)
        except (KnowledgeAuthError, KnowledgeRequestError) as exc:
            raise KnowledgeConfigError(str(exc)) from exc
        except KnowledgeServiceError as exc:
            raise KnowledgeUnavailable(str(exc)) from exc
        return KBDocument(
            doc_id=doc.doc_id,
            title=doc.doc_title,
            text=doc.text,
            kb_id=doc.kb_id,
            chunk_count=doc.chunk_count,
            truncated=doc.truncated,
        )

    async def ingest_document(
        self,
        kb_id: str,
        filename: str,
        content: bytes,
        *,
        content_type: str = "application/octet-stream",
    ) -> KBIngestResult:
        from kb_sdk import KnowledgeAuthError, KnowledgeRequestError, KnowledgeServiceError

        target = self._map_kb_ids([kb_id])[0]
        try:
            result = await self._client.ingest(
                target, filename, content, content_type=content_type
            )
        except (KnowledgeAuthError, KnowledgeRequestError) as exc:
            raise KnowledgeConfigError(str(exc)) from exc
        except KnowledgeServiceError as exc:
            raise KnowledgeUnavailable(str(exc)) from exc
        return KBIngestResult(
            doc_id=result.doc_id,
            title=result.title,
            parse_status=result.parse_status,
            queued=result.queued,
            review_required=result.review_required,
            audit_risk_level=result.audit_risk_level,
        )

    async def health(self) -> dict:
        from kb_sdk import KnowledgeServiceError

        try:
            payload = await self._client.health()
        except KnowledgeServiceError as exc:
            return {"provider": self.name, "status": "unavailable", "detail": str(exc)}
        return {"provider": self.name, "status": "ok", **payload}


def _as_kb_hit(hit) -> KBHit:
    """kb_sdk.Hit → 平台内部的 KBHit。"""
    return KBHit(
        kb_id=hit.kb_id,
        kb_file=hit.doc_title,
        content=hit.text,
        relevance=round(float(hit.score), 3),
        chunk_id=hit.chunk_id,
        doc_id=hit.doc_id,
        source_uri=hit.source_uri or "",
    )
