from __future__ import annotations

from typing import TYPE_CHECKING

from langchain.agents import create_agent as build_agent
from langchain_core.messages import HumanMessage
from langchain_core.tools import tool

from agent_platform.skills.base import BaseSkill

if TYPE_CHECKING:
    from langgraph.graph.state import CompiledStateGraph

    from agent_platform.models.provider import ModelProvider

SYSTEM_PROMPT = """\
你是一个综合分析助手，能够结合数据查询和合同审查两项能力：

工作流程：
1. 先通过数据查询验证合同相关数据（如金额、供应商历史等）
2. 再对合同条款进行风险审查
3. 将数据验证结果与条款审查结果综合，生成完整的分析报告

确保数据事实与合同条款交叉验证，给出有数据支撑的审查意见。"""

FALLBACK_PROMPT = """\
你是一个合同审查助手。对用户提供的合同进行条款分析和风险评估，给出修改建议。"""


class DataInformedContractReviewSkill(BaseSkill):
    @property
    def name(self) -> str:
        return "data_contract_review"

    @property
    def description(self) -> str:
        return "结合数据查询和合同审查，先验证合同相关数据，再进行条款风险分析并生成综合报告"

    @property
    def examples(self) -> list[str]:
        return [
            "帮我审查这份采购合同，并验证金额是否与系统数据一致",
            "审查合同并查询供应商历史交易数据",
        ]

    @property
    def dependencies(self) -> list[str]:
        return ["data_query", "contract_review"]

    def create_agent(self, model_provider: ModelProvider, checkpointer=None) -> CompiledStateGraph:
        model = model_provider.get_model()
        return build_agent(model, [], system_prompt=FALLBACK_PROMPT, checkpointer=checkpointer)

    def compose(
        self,
        skills: dict[str, BaseSkill],
        model_provider: ModelProvider,
    ) -> CompiledStateGraph | None:
        dq_skill = skills.get("data_query")
        cr_skill = skills.get("contract_review")
        if not dq_skill or not cr_skill:
            return None

        dq_agent = dq_skill.create_agent(model_provider, checkpointer=None)
        cr_agent = cr_skill.create_agent(model_provider, checkpointer=None)

        @tool
        async def query_data(query: str) -> str:
            """通过自然语言查询业务数据（如金额、供应商信息等）。"""
            result = await dq_agent.ainvoke(
                {"messages": [HumanMessage(content=query)]}
            )
            return result["messages"][-1].content

        @tool
        async def review_contract(contract_text: str) -> str:
            """对合同文本进行条款审查和风险评估。"""
            result = await cr_agent.ainvoke(
                {"messages": [HumanMessage(content=contract_text)]}
            )
            return result["messages"][-1].content

        model = model_provider.get_model()
        return build_agent(
            model, [query_data, review_contract], system_prompt=SYSTEM_PROMPT
        )


skill = DataInformedContractReviewSkill()
