"""知识库领域模型。

平台内部统一的知识库数据形状，与具体后端无关。各 Provider 负责把自家的响应翻译成
这些类型，因此换后端不会波及调用方——这是「迁移只改配置」的前提。
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class KBInfo:
    """一个可检索的知识库。"""

    kb_id: str
    name: str = ""
    description: str = ""
    document_count: int = 0


@dataclass(frozen=True)
class KBHit:
    """一条知识库命中证据。

    ``kb_file`` 与 ``relevance`` 的字段名沿用文档审阅既有的输出契约：审阅结果会回调给
    外部系统，改名会破坏下游消费方。
    """

    kb_id: str
    kb_file: str
    content: str
    relevance: float
    chunk_id: str = ""
    doc_id: str = ""
    source_uri: str = ""

    def as_dict(self) -> dict:
        """审阅流水线与工具层使用的扁平结构。"""
        return {
            "kb_id": self.kb_id,
            "kb_file": self.kb_file,
            "content": self.content,
            "relevance": self.relevance,
        }


@dataclass(frozen=True)
class KBSearchResult:
    """一次检索的结果与其能力完整性。

    ``degraded`` 非空表示检索链路上有后端不可用，命中可能偏少。调用方必须把它和
    「知识库里确实没有」区分开：把降级结果当作完整证据，在审阅这类场景会直接
    产出「无问题」的错误结论。
    """

    hits: list[KBHit] = field(default_factory=list)
    degraded: list[str] = field(default_factory=list)
    took_ms: float = 0.0

    @property
    def is_complete(self) -> bool:
        return not self.degraded


@dataclass(frozen=True)
class KBAnswer:
    """知识库直接给出的带引用答案。"""

    answer: str
    citations: list[KBHit] = field(default_factory=list)
    model: str = ""
    provider: str = ""
    degraded: list[str] = field(default_factory=list)
    grounded: bool = False


@dataclass(frozen=True)
class KBDocument:
    """资源全文。"""

    doc_id: str
    title: str
    text: str
    kb_id: str = ""
    chunk_count: int = 0
    truncated: bool = False


@dataclass(frozen=True)
class KBIngestResult:
    """写入知识库的结果。

    ``review_required`` 为 True 时文件已存入但尚未进入解析管线，需要人工放行。
    调用方不该假设写完就能立刻检索到。
    """

    doc_id: str
    title: str
    parse_status: str = ""
    queued: bool = False
    review_required: bool = True
    audit_risk_level: str = ""
