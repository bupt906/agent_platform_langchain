from __future__ import annotations

from typing import TYPE_CHECKING

from langchain.agents import create_agent
from langchain_core.tools import tool

from agent_platform.skills.base import BaseSkill
from agent_platform.skills.contract_review.tools import (
    assess_risk,
    check_clause,
    parse_contract,
)

if TYPE_CHECKING:
    from langgraph.graph.state import CompiledStateGraph

    from agent_platform.models.provider import ModelProvider

SYSTEM_PROMPT = """\
你是一个智能合同审查助手。你的职责是：

1. 解析合同文本，提取关键条款
2. 逐条检查风险点
3. 给出整体风险评估和修改建议

审查要点：
- 合同标的是否明确
- 价款和支付条件是否合理
- 违约责任是否对等
- 争议解决方式是否明确
- 是否存在不合理的免责条款
- 保密条款是否完善"""


@tool
async def extract_clauses(contract_text: str) -> str:
    """解析合同文本，提取各个条款。"""
    clauses = await parse_contract(contract_text)
    return "\n".join(f"{i+1}. {c}" for i, c in enumerate(clauses))


@tool
async def review_clause(clause_text: str) -> str:
    """审查单个合同条款的法律风险。"""
    result = await check_clause(clause_text)
    return (
        f"条款：{result.clause}\n"
        f"风险等级：{result.risk_level}\n"
        f"问题：{result.issue}\n"
        f"建议：{result.suggestion}"
    )


@tool
async def overall_risk_assessment(clause_findings: str) -> str:
    """基于所有条款审查结果，给出整体风险评估。"""
    findings = [line for line in clause_findings.strip().split("\n") if line.strip()]
    result = await assess_risk(findings)
    return (
        f"整体风险等级：{result['overall_risk']}\n"
        f"总结：{result['summary']}\n"
        f"建议：{result['recommendation']}"
    )


class ContractReviewSkill(BaseSkill):
    @property
    def name(self) -> str:
        return "contract_review"

    @property
    def description(self) -> str:
        return "智能合同审查，解析合同文本、逐条检查风险并给出修改建议"

    @property
    def examples(self) -> list[str]:
        return [
            "帮我审查这份合同",
            "这个合同的违约条款有什么风险？",
            "分析一下这份采购合同",
        ]

    def create_agent(self, model_provider: ModelProvider, checkpointer=None) -> CompiledStateGraph:
        model = model_provider.get_model()
        return create_agent(
            model,
            [extract_clauses, review_clause, overall_risk_assessment],
            system_prompt=SYSTEM_PROMPT,
            checkpointer=checkpointer,
        )


skill = ContractReviewSkill()
