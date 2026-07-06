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

    from agent_platform.core.deps import PlatformDeps
    from agent_platform.skills.base import BaseSkill

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


async def _emit(state: OrchestrationState, event: Any) -> None:
    q = state.get("event_queue")
    if q is not None:
        await q.put(event)


async def _run_skill_agent(
    skill: BaseSkill,
    model_provider: Any,
    query: str,
) -> str:
    agent = skill.create_agent(model_provider)
    result = await agent.ainvoke({"messages": [HumanMessage(content=query)]})
    return result["messages"][-1].content


def build_sequential_graph(
    subtasks: list[SubTask],
    skills: dict[str, BaseSkill],
    deps: PlatformDeps,
) -> CompiledStateGraph:
    builder = StateGraph(OrchestrationState)

    for st in subtasks:
        _st = st

        async def step_fn(state: OrchestrationState, _subtask: SubTask = _st) -> dict:
            await _emit(
                state,
                StepStartEvent(
                    step_id=_subtask.id,
                    skill_name=_subtask.skill_name,
                    description=_subtask.description,
                ),
            )
            query = _subtask.description
            results = state.get("subtask_results", {})
            if results:
                prev = list(results.values())[-1]
                query = f"{_subtask.description}\n\n参考前序结果：\n{prev}"

            skill = skills[_subtask.skill_name]
            output = await _run_skill_agent(skill, deps.model_provider, query)

            await _emit(
                state,
                StepDoneEvent(
                    step_id=_subtask.id,
                    skill_name=_subtask.skill_name,
                    result_summary=output[:200],
                ),
            )
            return {
                "subtask_results": {_subtask.id: output},
                "final_result": output,
            }

        builder.add_node(f"step_{_st.id}", step_fn)

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
        response = await model.with_structured_output(ExecutionPlan).ainvoke(
            [
                SystemMessage(
                    content=(
                        f"你是一个任务分解专家。将用户问题分解为可以并行执行的子任务。\n"
                        f"可用技能: {', '.join(skill_names)}\n"
                        f"返回 subtasks 列表。"
                    )
                ),
                HumanMessage(content=state["original_query"]),
            ]
        )
        for st in response.subtasks:
            await _emit(
                state,
                StepStartEvent(
                    step_id=st.id, skill_name=st.skill_name, description=st.description
                ),
            )
        return {"subtask_results": {"_plan": str([s.model_dump() for s in response.subtasks])}}

    async def execute_all(state: OrchestrationState) -> dict:
        import json

        plan_str = state["subtask_results"].get("_plan", "[]")
        try:
            plan_data = json.loads(plan_str.replace("'", '"'))
            dynamic_subtasks = [SubTask(**d) for d in plan_data]
        except Exception:
            dynamic_subtasks = subtasks

        async def run_one(st: SubTask) -> tuple[str, str]:
            skill = skills.get(st.skill_name)
            if not skill:
                return st.id, f"未找到技能: {st.skill_name}"
            output = await _run_skill_agent(skill, deps.model_provider, st.description)
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
        results = {k: v for k, v in state["subtask_results"].items() if not k.startswith("_")}
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
