from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Literal

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from agent_platform.graph.orchestration import OrchestrationEngine
from agent_platform.graph.patterns import ExecutionPlan, SubTask

if TYPE_CHECKING:
    from agent_platform.core.deps import PlatformDeps

logger = logging.getLogger(__name__)


class RouterDecision(BaseModel):
    """路由决策结果。"""

    skill_name: str
    rewritten_query: str
    confidence: float = Field(ge=0.0, le=1.0)
    mode: Literal["single", "multi"] = "single"
    execution_plan: ExecutionPlan | None = None


def _build_router_prompt(deps: PlatformDeps) -> str:
    skills = deps.skill_registry.list_skills()
    skill_descriptions = []
    for s in skills:
        dep_info = f"  依赖技能: {', '.join(s.dependencies)}" if s.dependencies else ""
        examples = "\n".join(f"    - {e}" for e in s.examples)
        skill_descriptions.append(
            f"- **{s.name}**: {s.description}\n"
            f"  示例问题:\n{examples}\n{dep_info}"
        )
    skills_text = "\n".join(skill_descriptions)

    return f"""\
你是一个智能路由器，负责分析用户意图并选择最合适的处理方式。

## 可用技能
{skills_text}

## 路由规则
1. 如果用户问题可以由单一技能处理，选择 mode="single"，填写对应 skill_name
2. 如果需要多个技能协同，选择 mode="multi"，skill_name 填 "multi_agent"，
   并提供 execution_plan：
   - mode: "sequential"（顺序执行）/ "parallel"（并行执行）/ "orchestrator"（动态编排）
   - subtasks: 子任务列表，每个包含 id、skill_name、description
3. 如果没有合适的技能匹配，skill_name 填 "general"，mode="single"
4. rewritten_query 是对用户原始问题的优化改写，使其更适合目标技能处理
5. confidence 是你对路由决策的置信度 (0.0-1.0)"""


async def resolve_route(
    message: str,
    deps: PlatformDeps,
    *,
    model_id: str | None = None,
) -> RouterDecision:
    """分析用户意图，返回路由决策。chat 端点的共享入口。"""
    model = deps.model_provider.get_model(model_id)
    structured_model = model.with_structured_output(RouterDecision)

    system_prompt = _build_router_prompt(deps)
    decision: RouterDecision = await structured_model.ainvoke(
        [SystemMessage(content=system_prompt), HumanMessage(content=message)]
    )

    logger.info(
        "路由决策: skill=%s, mode=%s, confidence=%.2f",
        decision.skill_name,
        decision.mode,
        decision.confidence,
    )
    return decision


async def execute_decision(
    decision: RouterDecision,
    message: str,
    deps: PlatformDeps,
    *,
    model_id: str | None = None,
    session_id: str | None = None,
) -> str:
    """执行路由决策，返回最终回复文本。"""
    invoke_cfg = _build_invoke_config(session_id)

    if decision.mode == "multi" and decision.execution_plan:
        engine = OrchestrationEngine(deps)
        return await engine.execute(message, decision.execution_plan)

    skill = deps.skill_registry.get(decision.skill_name)
    if skill:
        skills = deps.skill_registry.get_all_skills()
        agent = skill.compose(skills, deps.model_provider) or skill.create_agent(
            deps.model_provider, checkpointer=deps.checkpointer
        )
        result = await agent.ainvoke(
            {"messages": [HumanMessage(content=decision.rewritten_query)]},
            config=invoke_cfg,
        )
        return result["messages"][-1].content

    return await _general_response(message, deps, model_id, invoke_cfg)


async def execute_skill_direct(
    skill_name: str,
    message: str,
    deps: PlatformDeps,
    *,
    model_id: str | None = None,
    session_id: str | None = None,
) -> str:
    """跳过路由，直接调用指定技能。"""
    invoke_cfg = _build_invoke_config(session_id)
    skill = deps.skill_registry.get(skill_name)
    if not skill:
        return f"未找到技能: {skill_name}"

    skills = deps.skill_registry.get_all_skills()
    agent = skill.compose(skills, deps.model_provider) or skill.create_agent(
        deps.model_provider, checkpointer=deps.checkpointer
    )
    result = await agent.ainvoke(
        {"messages": [HumanMessage(content=message)]},
        config=invoke_cfg,
    )
    return result["messages"][-1].content


def _build_invoke_config(session_id: str | None) -> dict:
    """构建 LangGraph ainvoke 的 config dict。"""
    if session_id:
        return {"configurable": {"thread_id": session_id}}
    return {}


async def _general_response(
    message: str,
    deps: PlatformDeps,
    model_id: str | None = None,
    invoke_cfg: dict | None = None,
) -> str:
    model = deps.model_provider.get_model(model_id)
    result = await model.ainvoke(
        [
            SystemMessage(content="你是一个通用智能助手，尽力回答用户的问题。"),
            HumanMessage(content=message),
        ],
        config=invoke_cfg or {},
    )
    return result.content


# ── 向后兼容 ──────────────────────────────────────────────────


async def route_and_execute(
    message: str,
    deps: PlatformDeps,
    *,
    model_id: str | None = None,
    session_id: str | None = None,
) -> str:
    """分析意图 + 执行决策（单次调用便捷函数）。"""
    decision = await resolve_route(message, deps, model_id=model_id)
    return await execute_decision(decision, message, deps, model_id=model_id, session_id=session_id)
