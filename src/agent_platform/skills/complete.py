"""Complete 工具 — 声明式 Skill 的结构化输出入口。

每个 skill 在完成任务后必须调用对应的 complete 工具。
不同 skill 类型有不同的输出 schema。
"""

from __future__ import annotations

import json

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

# ── 通用 complete ────────────────────────────────────────────

class CompleteTaskInput(BaseModel):
    summary: str = Field(description="完成任务的简短摘要，1-3 句话概括做了什么和关键结论")
    detail: str = Field(default="", description="任务的详细结果，Markdown 格式")
    data_key: str = Field(default="", description="产出数据的引用 key")


# ── 按技能类型的专用 complete ──────────────────────────────

class SQLCompleteInput(BaseModel):
    summary: str = Field(description="结构化摘要：涉及的表名 + 关键数字 + 一句话概括")
    detail: str = Field(description="每条 SQL 的详细结果，包括 SQL 文本、返回行数列数、数据概括")
    sql_texts: list[str] = Field(default=[], description="执行的所有 SQL 语句列表")
    table_names: list[str] = Field(default=[], description="涉及的所有表名")
    data_key: str = Field(default="", description="主查询结果的 data_key")
    extra_data_keys: list[str] = Field(default=[], description="其他查询结果的 data_key")


class InfoCompleteInput(BaseModel):
    summary: str = Field(description="简短摘要，1-2 句话概括找到的信息")
    detail: str = Field(description="完整的检索结果信息")


class AnalyzeCompleteInput(BaseModel):
    summary: str = Field(description="关键发现列表，3-8 条，每条附具体数字")
    detail: str = Field(description="完整分析报告，Markdown 格式")
    data_key: str = Field(default="", description="数据引用 key")


class VisualizeCompleteInput(BaseModel):
    summary: str = Field(description="生成图表的描述，按编号列出")
    detail: str = Field(default="", description="图表解读说明")
    data_key: str = Field(default="", description="数据引用 key")


class TextAnalysisCompleteInput(BaseModel):
    summary: str = Field(description="分析结论摘要，3-5 条关键发现")
    detail: str = Field(description="完整分析结果，Markdown 格式")
    data_key: str = Field(default="", description="新生成数据集的 data_key")


# ── 工厂 ────────────────────────────────────────────────────

_COMPLETE_TOOLS: dict[str, StructuredTool] = {}


def _make_complete(name: str, schema: type[BaseModel], description: str) -> StructuredTool:
    def _complete(**kwargs) -> str:
        return json.dumps(
            {k: v for k, v in kwargs.items() if v is not None and v != []},
            ensure_ascii=False,
            default=str,
        )

    tool = StructuredTool.from_function(
        func=_complete,
        name=name,
        description=description,
        args_schema=schema,
    )
    _COMPLETE_TOOLS[name] = tool
    return tool


# 默认通用 complete
complete_task = _make_complete(
    "complete_task",
    CompleteTaskInput,
    "任务完成时必须调用此工具提交结果。summary 为 1-3 句话摘要，detail 包含完整结果。",
)

# 可选专用 complete（如果 skill 需要结构化输出）
complete_sql = _make_complete(
    "complete_sql",
    SQLCompleteInput,
    "SQL 查询任务完成时必须调用。提供摘要、详细结果、SQL 语句和数据引用。",
)

complete_info = _make_complete(
    "complete_info",
    InfoCompleteInput,
    "信息检索任务完成时必须调用。提供简短摘要和完整的检索结果。",
)

complete_analyze = _make_complete(
    "complete_analyze",
    AnalyzeCompleteInput,
    "数据分析任务完成时必须调用。提供发现列表和完整分析报告。",
)

complete_visualize = _make_complete(
    "complete_visualize",
    VisualizeCompleteInput,
    "可视化任务完成时必须调用。提供图表描述和数据引用。",
)

complete_text_analysis = _make_complete(
    "complete_text_analysis",
    TextAnalysisCompleteInput,
    "文本分析任务完成时必须调用。提供分析摘要和完整结果。",
)


def get_complete_tool(name: str) -> StructuredTool | None:
    return _COMPLETE_TOOLS.get(name)


def all_complete_tools() -> list[StructuredTool]:
    return list(_COMPLETE_TOOLS.values())
