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
    build_sequential_graph_with_hitl,
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
        hitl_enabled: bool = False,
        sensitive_skills: list[str] | None = None,
    ) -> str:
        skills: dict = {}
        for st in plan.subtasks:
            skill = self._deps.skill_registry.get(st.skill_name)
            if skill:
                skills[st.skill_name] = skill

        initial_state: OrchestrationState = {
            "original_query": query,
            "subtask_results": {},
            "final_result": "",
            "event_queue": event_queue,
            "approval_pending": "",
            "hitl_enabled": hitl_enabled,
        }

        if plan.mode == "sequential":
            if hitl_enabled and sensitive_skills:
                graph = build_sequential_graph_with_hitl(
                    plan.subtasks, skills, self._deps, sensitive_skills
                )
            else:
                graph = build_sequential_graph(plan.subtasks, skills, self._deps)
        elif plan.mode == "parallel":
            graph = build_parallel_graph(
                plan.subtasks, skills, self._deps, plan.synthesis_prompt
            )
        else:
            graph = build_orchestrator_worker_graph(
                plan.subtasks, skills, self._deps, plan.synthesis_prompt
            )

        try:
            result = await graph.ainvoke(initial_state)
            return result["final_result"]
        except Exception as e:
            # 检查是否是 GraphInterrupt（LangGraph HITL 中断）
            if "GraphInterrupt" in type(e).__name__ or "interrupt" in str(e).lower():
                logger.info("图执行被中断（HITL 审批），等待恢复")
                if event_queue is not None:
                    from agent_platform.hitl.events import ApprovalNeededEvent

                    await event_queue.put(
                        ApprovalNeededEvent(
                            approval_id="pending",
                            operation=plan.mode,
                            skill_name=",".join(skills.keys()),
                            details=str(e),
                        )
                    )
                return "操作需要人工审批，已发送审批请求。"
            raise
        finally:
            # 确保流式消费者能收到终止信号——即使 graph 执行失败也会推送
            if event_queue is not None:
                await event_queue.put(_SENTINEL)

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
                    # 带超时的等待，防止 sentinel 未入队导致永久阻塞
                    event = await asyncio.wait_for(event_queue.get(), timeout=300.0)
                except asyncio.TimeoutError:
                    logger.warning("编排流超时，强制终止")
                    break
                if event is _SENTINEL:
                    break
                yield event

            # 循环正常退出后检查 background task 是否抛出了异常
            exc = task.exception()
            if exc is not None:
                raise exc
        except Exception:
            if not task.done():
                task.cancel()
            raise
