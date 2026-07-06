"""示例工作流：合同审查流水线（使用 LangGraph StateGraph）。"""

from __future__ import annotations

from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel

from agent_platform.skills.contract_review.tools import (
    assess_risk,
    check_clause,
    parse_contract,
)


class ContractWorkflowOutput(BaseModel):
    report: str
    risk_level: str
    clause_count: int


def _replace(old: str, new: str) -> str:
    return new


class ContractWorkflowState(TypedDict):
    contract_text: str
    clauses: list[str]
    risk_findings: list[str]
    overall_risk: Annotated[str, _replace]
    final_report: Annotated[str, _replace]


async def parse_contract_node(state: ContractWorkflowState) -> dict:
    clauses = await parse_contract(state["contract_text"])
    return {"clauses": clauses}


async def review_clauses_node(state: ContractWorkflowState) -> dict:
    findings = []
    for clause in state["clauses"]:
        result = await check_clause(clause)
        if result.risk_level != "低":
            findings.append(
                f"{result.clause} | 风险: {result.risk_level} | {result.issue}"
            )
    return {"risk_findings": findings}


def should_assess_risk(state: ContractWorkflowState) -> str:
    if state.get("risk_findings"):
        return "risk_assessment"
    return "low_risk_end"


async def risk_assessment_node(state: ContractWorkflowState) -> dict:
    assessment = await assess_risk(state["risk_findings"])
    report = (
        f"# 合同审查报告\n\n"
        f"## 条款数量: {len(state['clauses'])}\n"
        f"## 风险条款: {len(state['risk_findings'])}\n\n"
        f"## 整体风险: {assessment['overall_risk']}\n"
        f"{assessment['summary']}\n\n"
        f"## 建议\n{assessment['recommendation']}"
    )
    return {"overall_risk": assessment["overall_risk"], "final_report": report}


async def low_risk_end_node(state: ContractWorkflowState) -> dict:
    report = (
        f"# 合同审查报告\n\n"
        f"## 条款数量: {len(state['clauses'])}\n"
        f"## 风险条款: 0\n\n"
        f"## 整体风险: 低\n"
        f"合同条款整体风险较低，未发现明显问题。"
    )
    return {"overall_risk": "低", "final_report": report}


def build_contract_review_graph() -> StateGraph:
    builder = StateGraph(ContractWorkflowState)
    builder.add_node("parse", parse_contract_node)
    builder.add_node("review", review_clauses_node)
    builder.add_node("risk_assessment", risk_assessment_node)
    builder.add_node("low_risk_end", low_risk_end_node)

    builder.add_edge(START, "parse")
    builder.add_edge("parse", "review")
    builder.add_conditional_edges("review", should_assess_risk)
    builder.add_edge("risk_assessment", END)
    builder.add_edge("low_risk_end", END)

    return builder


async def run_contract_review_workflow(
    contract_text: str,
) -> ContractWorkflowOutput:
    graph = build_contract_review_graph().compile()
    result = await graph.ainvoke(
        {
            "contract_text": contract_text,
            "clauses": [],
            "risk_findings": [],
            "overall_risk": "",
            "final_report": "",
        }
    )
    return ContractWorkflowOutput(
        report=result["final_report"],
        risk_level=result["overall_risk"],
        clause_count=len(result["clauses"]),
    )
