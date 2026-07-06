from __future__ import annotations

from typing import TYPE_CHECKING

from langchain.agents import create_agent
from langchain_core.tools import tool

from agent_platform.skills.base import BaseSkill
from agent_platform.skills.qa.tools import knowledge_search

if TYPE_CHECKING:
    from langgraph.graph.state import CompiledStateGraph

    from agent_platform.models.provider import ModelProvider

SYSTEM_PROMPT = """\
你是一个智能问答助手。根据用户的问题，先从知识库中检索相关信息，再基于检索结果给出准确的回答。

回答要求：
1. 优先使用知识库中的信息
2. 如果知识库中没有相关信息，请明确告知用户
3. 回答要简洁、准确、有条理"""


@tool
async def search_knowledge(query: str, top_k: int = 5) -> str:
    """从知识库中检索与用户问题相关的文档。"""
    results = await knowledge_search(query, top_k)
    if not results:
        return "知识库中未找到相关信息"
    parts = []
    for r in results:
        parts.append(f"[来源: {r['source']}] (相关度: {r['score']})\n{r['content']}")
    return "\n\n---\n\n".join(parts)


class QASkill(BaseSkill):
    @property
    def name(self) -> str:
        return "qa"

    @property
    def description(self) -> str:
        return "通用知识问答，基于 RAG 检索知识库回答用户问题"

    @property
    def examples(self) -> list[str]:
        return [
            "公司的请假制度是什么？",
            "项目的技术架构是怎样的？",
            "帮我查一下相关的政策文件",
        ]

    def create_agent(self, model_provider: ModelProvider, checkpointer=None) -> CompiledStateGraph:
        model = model_provider.get_model()
        return create_agent(model, [search_knowledge], system_prompt=SYSTEM_PROMPT, checkpointer=checkpointer)


skill = QASkill()
