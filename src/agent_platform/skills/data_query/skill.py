from __future__ import annotations

from typing import TYPE_CHECKING

from langchain.agents import create_agent
from langchain_core.tools import tool

from agent_platform.skills.base import BaseSkill
from agent_platform.skills.data_query.tools import execute_sql, get_table_schema

if TYPE_CHECKING:
    from langgraph.graph.state import CompiledStateGraph

    from agent_platform.models.provider import ModelProvider

SYSTEM_PROMPT = """\
你是一个数据查询助手（问数智能体）。用户用自然语言描述数据需求，你需要：

1. 先理解用户的查询意图
2. 查看相关表结构
3. 生成正确的 SQL 查询
4. 执行查询并解读结果
5. 用自然语言回答用户

注意事项：
- 只生成 SELECT 查询，禁止 INSERT/UPDATE/DELETE
- SQL 要考虑性能，避免全表扫描
- 结果要用通俗语言解读，不要只返回原始数据"""


@tool
async def query_table_schema(table_name: str) -> str:
    """查看数据库表的结构定义。"""
    return await get_table_schema(table_name)


@tool
async def run_sql_query(sql: str) -> str:
    """执行 SQL 查询语句。只允许 SELECT 查询。"""
    import re

    cleaned = re.sub(r"(--[^\n]*|/\*.*?\*/)", "", sql, flags=re.DOTALL).strip()
    first_word = cleaned.upper().split()[0] if cleaned.split() else ""
    if first_word != "SELECT":
        return f"错误：只允许执行 SELECT 查询"
    rows = await execute_sql(sql)
    if not rows:
        return "查询无结果"
    headers = list(rows[0].keys())
    lines = [" | ".join(headers)]
    lines.append(" | ".join("---" for _ in headers))
    for row in rows:
        lines.append(" | ".join(str(row.get(h, "")) for h in headers))
    return "\n".join(lines)


class DataQuerySkill(BaseSkill):
    @property
    def name(self) -> str:
        return "data_query"

    @property
    def description(self) -> str:
        return "自然语言问数，将用户问题转为 SQL 查询并返回数据分析结果"

    @property
    def examples(self) -> list[str]:
        return [
            "上个月销售额是多少？",
            "哪个部门人数最多？",
            "查询订单状态分布",
        ]

    def create_agent(self, model_provider: ModelProvider, checkpointer=None) -> CompiledStateGraph:
        model = model_provider.get_model()
        return create_agent(
            model, [query_table_schema, run_sql_query], system_prompt=SYSTEM_PROMPT, checkpointer=checkpointer
        )


skill = DataQuerySkill()
