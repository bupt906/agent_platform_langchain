"""知识库能力接口。

平台里所有需要知识库的地方都只依赖这个接口，不依赖具体后端。新增一个后端＝新增一个
实现类＋改一个配置项，调用方（Agent、Skill、工具、审阅流水线）一行都不用动。

各实现必须遵守两条约定：

1. **失败要抛，不要静默返回空。** 空列表的含义是「知识库里没有」；检索失败必须抛
   :class:`KnowledgeUnavailable`。在文档审阅里这两者的区别是「无问题」和「没查成」，
   把后者当成前者会直接产出错误结论。
2. **降级要上报。** 后端部分不可用时填 ``KBSearchResult.degraded``，不要假装完整。
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from agent_platform.knowledge.models import (
    KBAnswer,
    KBDocument,
    KBInfo,
    KBIngestResult,
    KBSearchResult,
)


class KnowledgeError(RuntimeError):
    """知识库调用失败的基类。"""


class KnowledgeUnavailable(KnowledgeError):
    """后端不可达、超时或返回错误。可重试。"""


class KnowledgeConfigError(KnowledgeError):
    """配置问题：密钥无效、服务未开通、知识库 ID 不存在。重试无意义。"""


class KnowledgeProvider(ABC):
    """知识库后端的统一接口。"""

    #: 供日志与审计使用的后端标识。
    name: str = "unknown"

    @abstractmethod
    async def search(
        self,
        kb_ids: list[str],
        query: str,
        *,
        top_k: int | None = None,
    ) -> KBSearchResult:
        """检索知识库，返回按相关度降序的证据。"""

    @abstractmethod
    async def list_kbs(self) -> list[KBInfo]:
        """列出可检索的知识库。不支持的后端返回空列表。"""

    async def answer(
        self,
        question: str,
        kb_ids: list[str],
        *,
        top_k: int | None = None,
    ) -> KBAnswer:
        """由知识库直接作答。

        默认实现声明不支持；能在服务端完成 RAG 的后端应当覆盖它，
        以省掉一次「取回证据再自己拼 prompt」的往返。
        """
        raise KnowledgeConfigError(f"后端 {self.name} 不支持服务端问答")

    async def fetch_document(self, doc_id: str) -> KBDocument:
        """取回资源全文。不支持的后端抛出 :class:`KnowledgeConfigError`。"""
        raise KnowledgeConfigError(f"后端 {self.name} 不支持取回全文")

    async def ingest_document(
        self,
        kb_id: str,
        filename: str,
        content: bytes,
        *,
        content_type: str = "application/octet-stream",
    ) -> KBIngestResult:
        """把一份文件写入知识库。不支持的后端抛出 :class:`KnowledgeConfigError`。"""
        raise KnowledgeConfigError(f"后端 {self.name} 不支持写入知识库")

    async def health(self) -> dict:
        """连通性自检。"""
        return {"provider": self.name, "status": "unknown"}
