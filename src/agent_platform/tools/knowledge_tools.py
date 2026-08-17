"""知识库工具 —— 注册进全局工具表，供所有 Agent 与声明式 Skill 使用。

这是「知识库能力对所有智能体可用」的落点。注册之后：

- 声明式 Skill 在 ``SKILL.md`` frontmatter 里写 ``tools: [search_knowledge]`` 即可绑定，
  启动时由 ``resolve_skill_tools`` 校验；
- 代码型 Agent 用 ``tools.registry.get_many(["search_knowledge"])`` 取用；
- 两者都不需要知道后端是万悟还是知识库中台。

**失败必须让模型看见。** 这些工具在检索失败时返回明确的错误文本，绝不返回「没有找到」。
两者对模型是完全不同的信号：前者意味着「这次没查成，别下结论」，后者意味着「知识库里
确实没有」。把前者伪装成后者，在文档审阅这类场景会直接产出「无问题」的错误结论。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from langchain_core.tools import tool

from agent_platform.knowledge.provider import KnowledgeError
from agent_platform.tools.registry import register_all

if TYPE_CHECKING:
    from agent_platform.knowledge.models import KBHit
    from agent_platform.knowledge.provider import KnowledgeProvider

logger = logging.getLogger(__name__)

_MAX_SNIPPET_CHARS = 800


def _parse_kb_ids(raw: str) -> list[str]:
    return [item.strip() for item in (raw or "").split(",") if item.strip()]


def _format_degraded(degraded: list[str]) -> str:
    if not degraded:
        return ""
    return (
        f"\n\n⚠️ 本次检索能力不完整，以下后端不可用：{', '.join(degraded)}。"
        f"命中结果可能偏少，不要据此断定知识库中没有相关内容。"
    )


def _format_hits(hits: list[KBHit], degraded: list[str]) -> str:
    if not hits:
        return "未检索到相关内容。" + _format_degraded(degraded)
    parts = []
    for index, hit in enumerate(hits, start=1):
        content = hit.content[:_MAX_SNIPPET_CHARS]
        parts.append(
            f"### 证据 {index}（知识库：{hit.kb_id}，文件：{hit.kb_file}，"
            f"相关度：{hit.relevance}）\n{content}"
        )
    return "\n\n".join(parts) + _format_degraded(degraded)


def register_knowledge_tools(knowledge: KnowledgeProvider) -> None:
    """把知识库能力注册为全局工具。在 app lifespan 中调用。"""

    @tool
    async def search_knowledge(query: str, kb_ids: str = "", top_k: int = 5) -> str:
        """检索企业知识库，返回与问题最相关的原文证据。

        需要事实依据、行业标准、规章制度或历史文档内容时使用。返回的是原文片段，
        请基于这些片段回答，不要脱离证据自行推断。

        Args:
            query: 检索问题或关键词
            kb_ids: 知识库 ID 列表，逗号分隔；留空表示检索全部可访问的知识库
            top_k: 返回的证据条数，默认 5
        """
        try:
            result = await knowledge.search(_parse_kb_ids(kb_ids), query, top_k=top_k)
        except KnowledgeError as exc:
            logger.warning("search_knowledge 失败: %s", exc)
            return (
                f"知识库检索失败：{exc}\n"
                f"这不表示知识库中没有相关内容，请不要据此下结论。"
            )
        return _format_hits(result.hits, result.degraded)

    @tool
    async def answer_from_knowledge(question: str, kb_ids: str = "") -> str:
        """让知识库直接回答问题，返回带引用来源的答案。

        适合可以一步答完的事实性问题。需要自己综合多条证据做判断时，改用
        search_knowledge 取回原文。

        Args:
            question: 要回答的问题
            kb_ids: 知识库 ID 列表，逗号分隔；留空表示使用全部可访问的知识库
        """
        try:
            result = await knowledge.answer(question, _parse_kb_ids(kb_ids))
        except KnowledgeError as exc:
            logger.warning("answer_from_knowledge 失败: %s", exc)
            return (
                f"知识库问答失败：{exc}\n"
                f"这不表示知识库中没有相关内容，请不要据此下结论。"
            )
        if not result.grounded or not result.answer:
            return "知识库中没有找到足以回答该问题的证据。" + _format_degraded(result.degraded)
        sources = "、".join(dict.fromkeys(hit.kb_file for hit in result.citations)) or "未标注"
        return f"{result.answer}\n\n来源：{sources}" + _format_degraded(result.degraded)

    @tool
    async def list_knowledge_bases() -> str:
        """列出当前可检索的知识库及其编号。

        不确定该在哪个知识库里查时先调用它，再把选中的编号传给 search_knowledge。
        """
        try:
            items = await knowledge.list_kbs()
        except KnowledgeError as exc:
            logger.warning("list_knowledge_bases 失败: %s", exc)
            return f"获取知识库列表失败：{exc}"
        if not items:
            return (
                "当前后端不提供知识库清单，请直接向 search_knowledge 传入已知的知识库 ID。"
            )
        lines = [
            f"- {item.name or item.kb_id}（ID：{item.kb_id}，文档数：{item.document_count}）"
            + (f"：{item.description}" if item.description else "")
            for item in items
        ]
        return "可检索的知识库：\n" + "\n".join(lines)

    @tool
    async def fetch_knowledge_document(doc_id: str) -> str:
        """按原文顺序取回知识库中某个文档的全文。

        需要通读整篇而不是若干片段时使用——例如总结一份文件、逐条核对条款。
        doc_id 来自 search_knowledge 结果中的证据来源。

        Args:
            doc_id: 文档 ID
        """
        try:
            doc = await knowledge.fetch_document(doc_id)
        except KnowledgeError as exc:
            logger.warning("fetch_knowledge_document 失败: %s", exc)
            return f"取回文档失败：{exc}"
        suffix = "\n\n（全文过长，以上为截断内容）" if doc.truncated else ""
        return f"# {doc.title}\n\n{doc.text}{suffix}"

    @tool
    async def add_to_knowledge_base(kb_id: str, filename: str, content: str) -> str:
        """把一段文本作为新文档写入知识库，供后续检索。

        用于沉淀本次产出的知识（如抽取的图谱、整理的结论）。写入是有副作用的操作，
        只在用户明确要求保存时调用。

        Args:
            kb_id: 目标知识库 ID，可用 list_knowledge_bases 查询
            filename: 文件名，需带扩展名（如 "设备故障总结.md"）
            content: 文档正文
        """
        try:
            result = await knowledge.ingest_document(
                kb_id, filename, content.encode("utf-8"), content_type="text/markdown"
            )
        except KnowledgeError as exc:
            logger.warning("add_to_knowledge_base 失败: %s", exc)
            return f"写入知识库失败：{exc}"
        if result.review_required:
            return (
                f"《{result.title}》已提交到知识库，但需要管理员在入库审核中放行后才能被检索"
                f"（内容风险等级：{result.audit_risk_level or '未知'}）。文档 ID：{result.doc_id}"
            )
        return (
            f"《{result.title}》已写入知识库并进入解析队列，解析完成后即可检索。"
            f"文档 ID：{result.doc_id}"
        )

    register_all([
        search_knowledge,
        answer_from_knowledge,
        list_knowledge_bases,
        fetch_knowledge_document,
        add_to_knowledge_base,
    ])
    logger.info(
        "知识库工具已注册（后端 %s）: search_knowledge, answer_from_knowledge, "
        "list_knowledge_bases, fetch_knowledge_document, add_to_knowledge_base",
        knowledge.name,
    )
