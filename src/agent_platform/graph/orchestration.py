from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, AsyncIterator

from agent_platform.graph.events import OrchestrationEvent
from agent_platform.graph.patterns import (
    ExecutionPlan,
    OrchestrationState,
    build_orchestrator_worker_graph,
    build_parallel_graph,
    build_sequential_graph,
)

if TYPE_CHECKING:
    from agent_platform.core.deps import PlatformDeps

logger = logging.getLogger(__name__)

_SENTINEL = object()


class OrchestrationEngine:
    """多 Agent 编排引擎，根据 ExecutionPlan 选择编排模式并执行。"""

    def __init__(self, deps: PlatformDeps) -> None:
        self._deps = deps

    async def execute(
        self,
        query: str,
        plan: ExecutionPlan,
        *,
        event_queue: asyncio.Queue | None = None,
    ) -> str:
        skills = {}
        for st in plan.subtasks:
            skill = self._deps.skill_registry.get(st.skill_name)
            if skill:
                skills[st.skill_name] = skill

        initial_state: OrchestrationState = {
            "original_query": query,
            "subtask_results": {},
            "final_result": "",
            "event_queue": event_queue,
        }

        if plan.mode == "sequential":
            graph = build_sequential_graph(plan.subtasks, skills, self._deps)
        elif plan.mode == "parallel":
            graph = build_parallel_graph(
                plan.subtasks, skills, self._deps, plan.synthesis_prompt
            )
        else:
            graph = build_orchestrator_worker_graph(
                plan.subtasks, skills, self._deps, plan.synthesis_prompt
            )

        result = await graph.ainvoke(initial_state)
        return result["final_result"]

    async def execute_stream(
        self,
        query: str,
        plan: ExecutionPlan,
    ) -> AsyncIterator[OrchestrationEvent]:
        event_queue: asyncio.Queue = asyncio.Queue()
        task = asyncio.create_task(
            self.execute(query, plan, event_queue=event_queue)
        )

        try:
            while True:
                try:
                    event = await asyncio.wait_for(event_queue.get(), timeout=0.5)
                except asyncio.TimeoutError:
                    if task.done():
                        break
                    continue

                if event is _SENTINEL:
                    break
                yield event

            if task.done():
                task.result()
        except Exception:
            task.cancel()
            raise
