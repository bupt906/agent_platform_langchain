"""AI 文档审阅技能。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from langchain.agents import create_agent
from langchain_core.tools import tool

from agent_platform.agents.base import BaseSkill

if TYPE_CHECKING:
    from langgraph.graph.state import CompiledStateGraph

    from agent_platform.models.provider import ModelProvider

SYSTEM_PROMPT = """\
你是 AI 文档审阅专家，专门审查矿山行业文档的合规性、用词规范、技术准确性和场景适配性。

## 工作方式
用户会提供需要审阅的文件路径和知识库 ID 列表。你需要使用 review_document 工具执行逐句审查，然后向用户解读审查结果。

## 审查规则
- 仅以知识库标准为准，不引入外部知识
- 每条判断必须有知识库依据"""


class DocumentReviewSkill(BaseSkill):
    """AI 文档审阅技能。"""

    @property
    def name(self) -> str:
        return "document_review"

    @property
    def description(self) -> str:
        return "AI 文档审阅：按句子粒度审查文档，基于知识库标准判断合规性、用词规范、技术准确性和场景适配性"

    @property
    def examples(self) -> list[str]:
        return [
            "帮我审查这份安全生产方案，用合规性和技术标准知识库",
            "审查这份报告的用词规范性",
        ]

    @property
    def tool_config(self) -> dict:
        return {"timeout": 120.0, "parallel": False}

    def create_agent(self, model_provider: ModelProvider, checkpointer=None) -> CompiledStateGraph:
        @tool
        async def review_document(file_path: str, kb_ids: str) -> str:
            """对文档执行逐句审阅。

            Args:
                file_path: 待审阅文件的完整路径（支持 txt/md/docx）
                kb_ids: 知识库 ID 列表，逗号分隔（如 "compliance,terminology"）
            """
            import json

            kb_list = [k.strip() for k in kb_ids.split(",") if k.strip()]
            from agent_platform.agents.document_review.pipeline import run_review_pipeline

            # _deps 由 router 在 compose/create_agent 调用前设置
            result = await run_review_pipeline(file_path, kb_list, _skill_deps)
            return json.dumps(result, ensure_ascii=False, indent=2)

        model = model_provider.get_model()
        return create_agent(model, [review_document], system_prompt=SYSTEM_PROMPT, checkpointer=checkpointer)


_skill_deps = None  # 由外部设置
skill = DocumentReviewSkill()
