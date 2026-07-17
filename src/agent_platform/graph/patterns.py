from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Annotated, Any, TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel

from agent_platform.graph.events import (
    StepDoneEvent,
    StepStartEvent,
    SynthesisDeltaEvent,
    SynthesisStartEvent,
)

if TYPE_CHECKING:
    from langgraph.graph.state import CompiledStateGraph

    from agent_platform.agents.base import BaseSkill
    from agent_platform.core.deps import PlatformDeps

logger = logging.getLogger(__name__)


class SubTask(BaseModel):
    id: str
    skill_name: str
    description: str
    depends_on: list[str] = []


class ExecutionPlan(BaseModel):
    mode: str  # "sequential" | "parallel" | "orchestrator"
    subtasks: list[SubTask]
    synthesis_prompt: str = "请综合以上各步骤的结果，给出完整的分析回答。"


def _merge_results(existing: dict[str, str], new: dict[str, str]) -> dict[str, str]:
    merged = dict(existing)
    merged.update(new)
    return merged


class OrchestrationState(TypedDict):
    original_query: str
    subtask_results: Annotated[dict[str, str], _merge_results]
    final_result: str
    event_queue: Any
    approval_pending: str  # 空字符串 = 无审批，否则为 approval_id
    hitl_enabled: bool


async def _emit(state: OrchestrationState, event: Any) -> None:
    q = state.get("event_queue")
    if q is not None:
        await q.put(event)


async def _run_skill_agent(
    skill: BaseSkill,
    model_provider: Any,
    query: str,
) -> str:
    agent = skill.create_agent(model_provider, checkpointer=None)
    result = await agent.ainvoke({"messages": [HumanMessage(content=query)]})
    return result["messages"][-1].content


# ── 工厂函数：避免 Python 闭包延迟绑定 ──────────────────────────


def _make_sequential_step(
    subtask: SubTask,
    skills: dict[str, BaseSkill],
    deps: PlatformDeps,
    *,
    include_previous: bool = True,
):
    """返回一个 LangGraph node 函数，执行单个子任务。"""

    async def step_fn(state: OrchestrationState) -> dict:
        await _emit(
            state,
            StepStartEvent(
                step_id=subtask.id,
                skill_name=subtask.skill_name,
                description=subtask.description,
            ),
        )
        query = subtask.description
        if include_previous:
            existing_results = state.get("subtask_results", {})
            if existing_results:
                prev = list(existing_results.values())[-1]
                query = f"{subtask.description}\n\n参考前序结果：\n{prev}"

        skill = skills[subtask.skill_name]
        output = await _run_skill_agent(skill, deps.model_provider, query)

        await _emit(
            state,
            StepDoneEvent(
                step_id=subtask.id,
                skill_name=subtask.skill_name,
                result_summary=output[:200],
            ),
        )
        return {
            "subtask_results": {subtask.id: output},
            "final_result": output,
        }

    return step_fn


# ── 编排图构建 ──────────────────────────────────────────────────


# ── HITL 审批门控节点 ──────────────────────────────────────


def _make_approval_gate(
    skill_name: str,
    operation: str,
):
    """返回一个 LangGraph node 函数，在执行敏感操作前触发审批中断。

    使用 LangGraph 的 interrupt() 函数挂起执行，等待外部 Command(resume=...) 恢复。
    """

    async def gate_fn(state: OrchestrationState) -> dict:
        from langgraph.types import interrupt

        if not state.get("hitl_enabled", False):
            return {}

        approval_details = f"技能 '{skill_name}' 请求执行操作: {operation}\n\n请确认是否继续？"
        # interrupt() 会在此处挂起图执行
        approved = interrupt(approval_details)

        if not approved:
            return {
                "final_result": f"操作已被拒绝: {operation}",
                "approval_pending": "rejected",
            }
        return {"approval_pending": ""}

    return gate_fn


# ── 编排图构建 ──────────────────────────────────────────────────


def build_sequential_graph_with_hitl(
    subtasks: list[SubTask],
    skills: dict[str, BaseSkill],
    deps: PlatformDeps,
    sensitive_skills: list[str] | None = None,
) -> CompiledStateGraph:
    """构建带 HITL 审批门控的顺序执行图。

    对于 sensitive_skills 列表中的技能，在执行前插入审批节点。
    """
    sensitive = set(sensitive_skills or [])

    builder = StateGraph(OrchestrationState)

    prev_name = START
    for i, st in enumerate(subtasks):
        # 如果技能需要审批，先插入审批门控节点
        if st.skill_name in sensitive:
            gate_name = f"approval_{st.id}"
            gate_fn = _make_approval_gate(st.skill_name, st.description)
            builder.add_node(gate_name, gate_fn)
            builder.add_edge(prev_name, gate_name)
            prev_name = gate_name

        node_fn = _make_sequential_step(st, skills, deps, include_previous=(i > 0))
        step_name = f"step_{st.id}"
        builder.add_node(step_name, node_fn)
        builder.add_edge(prev_name, step_name)
        prev_name = step_name

    builder.add_edge(prev_name, END)
    return builder.compile()


def build_sequential_graph(
    subtasks: list[SubTask],
    skills: dict[str, BaseSkill],
    deps: PlatformDeps,
) -> CompiledStateGraph:
    builder = StateGraph(OrchestrationState)

    for i, st in enumerate(subtasks):
        # 只有第一个 step 不注入前序结果
        node_fn = _make_sequential_step(st, skills, deps, include_previous=(i > 0))
        builder.add_node(f"step_{st.id}", node_fn)

    prev_name = START
    for st in subtasks:
        node_name = f"step_{st.id}"
        builder.add_edge(prev_name, node_name)
        prev_name = node_name
    builder.add_edge(prev_name, END)

    return builder.compile()


def build_parallel_graph(
    subtasks: list[SubTask],
    skills: dict[str, BaseSkill],
    deps: PlatformDeps,
    synthesis_prompt: str = "请综合以上各步骤的结果，给出完整的分析回答。",
) -> CompiledStateGraph:
    builder = StateGraph(OrchestrationState)

    async def execute_all(state: OrchestrationState) -> dict:
        async def run_one(st: SubTask) -> tuple[str, str]:
            await _emit(
                state,
                StepStartEvent(
                    step_id=st.id,
                    skill_name=st.skill_name,
                    description=st.description,
                ),
            )
            skill = skills[st.skill_name]
            output = await _run_skill_agent(
                skill, deps.model_provider, st.description
            )
            await _emit(
                state,
                StepDoneEvent(
                    step_id=st.id,
                    skill_name=st.skill_name,
                    result_summary=output[:200],
                ),
            )
            return st.id, output

        results = await asyncio.gather(*(run_one(st) for st in subtasks))
        return {"subtask_results": dict(results)}

    async def synthesize(state: OrchestrationState) -> dict:
        await _emit(state, SynthesisStartEvent())
        results = state["subtask_results"]
        parts = [f"## {k}\n{v}" for k, v in results.items()]
        context = "\n\n".join(parts)

        model = deps.model_provider.get_model()
        response = await model.ainvoke(
            [
                SystemMessage(content=synthesis_prompt),
                HumanMessage(
                    content=f"原始问题：{state['original_query']}\n\n各步骤结果：\n{context}"
                ),
            ]
        )
        content = response.content
        await _emit(state, SynthesisDeltaEvent(content=content))
        return {"final_result": content}

    builder.add_node("execute_all", execute_all)
    builder.add_node("synthesize", synthesize)
    builder.add_edge(START, "execute_all")
    builder.add_edge("execute_all", "synthesize")
    builder.add_edge("synthesize", END)

    return builder.compile()


def build_orchestrator_worker_graph(
    subtasks: list[SubTask],
    skills: dict[str, BaseSkill],
    deps: PlatformDeps,
    synthesis_prompt: str = "请综合以上各步骤的结果，给出完整的分析回答。",
) -> CompiledStateGraph:
    builder = StateGraph(OrchestrationState)

    async def decompose(state: OrchestrationState) -> dict:
        model = deps.model_provider.get_model()
        skill_names = list(skills.keys())
        response: ExecutionPlan = await model.with_structured_output(
            ExecutionPlan, method="json_mode"
        ).ainvoke(
            [
                SystemMessage(
                    content=(
                        "你是一个任务分解专家。将用户问题分解为可以并行执行的子任务。\n"
                        f"可用技能: {', '.join(skill_names)}\n"
                        "返回 subtasks 列表（json 格式）。"
                    )
                ),
                HumanMessage(content=state["original_query"]),
            ]
        )
        for st in response.subtasks:
            await _emit(
                state,
                StepStartEvent(
                    step_id=st.id,
                    skill_name=st.skill_name,
                    description=st.description,
                ),
            )
        # 直接存储 SubTask.model_dump() 列表，不再序列化为 JSON 字符串
        return {
            "subtask_results": {
                "_plan": [s.model_dump() for s in response.subtasks]  # type: ignore[dict-item]
            }
        }

    async def execute_all(state: OrchestrationState) -> dict:
        plan_data = state["subtask_results"].get("_plan", [])  # type: ignore[list-item]

        # plan_data 是 model_dump list；兼容旧版 JSON 字符串格式
        if isinstance(plan_data, str):
            import json

            plan_data = json.loads(plan_data)
        elif not isinstance(plan_data, list):
            plan_data = []

        dynamic_subtasks = [SubTask(**d) for d in plan_data] if plan_data else subtasks

        async def run_one(st: SubTask) -> tuple[str, str]:
            skill = skills.get(st.skill_name)
            if not skill:
                return st.id, f"未找到技能: {st.skill_name}"
            output = await _run_skill_agent(
                skill, deps.model_provider, st.description
            )
            await _emit(
                state,
                StepDoneEvent(
                    step_id=st.id,
                    skill_name=st.skill_name,
                    result_summary=output[:200],
                ),
            )
            return st.id, output

        results = await asyncio.gather(*(run_one(st) for st in dynamic_subtasks))
        return {"subtask_results": {k: v for k, v in results}}

    async def synthesize(state: OrchestrationState) -> dict:
        await _emit(state, SynthesisStartEvent())
        results = {
            k: v
            for k, v in state["subtask_results"].items()
            if not k.startswith("_")
        }
        parts = [f"## {k}\n{v}" for k, v in results.items()]
        context = "\n\n".join(parts)

        model = deps.model_provider.get_model()
        response = await model.ainvoke(
            [
                SystemMessage(content=synthesis_prompt),
                HumanMessage(
                    content=f"原始问题：{state['original_query']}\n\n各步骤结果：\n{context}"
                ),
            ]
        )
        content = response.content
        await _emit(state, SynthesisDeltaEvent(content=content))
        return {"final_result": content}

    builder.add_node("decompose", decompose)
    builder.add_node("execute_all", execute_all)
    builder.add_node("synthesize", synthesize)
    builder.add_edge(START, "decompose")
    builder.add_edge("decompose", "execute_all")
    builder.add_edge("execute_all", "synthesize")
    builder.add_edge("synthesize", END)

    return builder.compile()
