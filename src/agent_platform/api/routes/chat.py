from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Request
from langchain_core.messages import HumanMessage, SystemMessage
from sse_starlette.sse import EventSourceResponse

from agent_platform.api.schemas import ChatRequest, ChatResponse
from agent_platform.core.deps import PlatformDeps
from agent_platform.core.router import (
    RouterDecision,
    execute_decision,
    execute_skill_direct,
    resolve_route,
)
from agent_platform.graph.orchestration import OrchestrationEngine

logger = logging.getLogger(__name__)

router = APIRouter()


def _get_deps(request: Request) -> PlatformDeps:
    return request.app.state.deps


# ── 同步对话 ────────────────────────────────────────────────────


@router.post("/chat", response_model=ChatResponse)
async def chat(request: Request, body: ChatRequest) -> ChatResponse:
    deps = _get_deps(request)

    if body.skill:
        # 显式指定技能：跳过路由
        reply = await execute_skill_direct(
            body.skill,
            body.message,
            deps,
            model_id=body.model,
            session_id=body.session_id,
        )
        return ChatResponse(reply=reply, skill_used=body.skill)

    # 自动路由
    decision = await resolve_route(body.message, deps, model_id=body.model)
    reply = await execute_decision(
        decision,
        body.message,
        deps,
        model_id=body.model,
        session_id=body.session_id,
    )
    return ChatResponse(reply=reply, skill_used=decision.skill_name)


# ── 流式对话 ────────────────────────────────────────────────────


@router.post("/chat/stream")
async def chat_stream(request: Request, body: ChatRequest) -> EventSourceResponse:
    deps = _get_deps(request)

    async def event_generator():
        if body.skill:
            skill_name = body.skill
            decision = None
        else:
            decision = await resolve_route(body.message, deps, model_id=body.model)
            skill_name = decision.skill_name
            yield _sse("routing", type="routing", skill=skill_name, mode=decision.mode, confidence=decision.confidence)

        # ── 多 Agent 编排流式 ──
        is_multi = decision and decision.mode == "multi" and decision.execution_plan
        if is_multi:
            plan = decision.execution_plan
            yield _sse("plan", type="plan", mode=plan.mode, subtasks=[s.model_dump() for s in plan.subtasks])

            engine = OrchestrationEngine(deps)
            async for event in engine.execute_stream(body.message, plan):
                yield _sse(event.type, **event.to_dict())

            yield _sse("done", type="done", skill="multi_agent")
            return

        # ── 单技能 / 通用流式 ──
        skill = deps.skill_registry.get(skill_name)
        if not skill:
            # 通用对话 —— 检查技能手册
            system_content = "你是一个通用智能助手，尽力回答用户的问题。"
            if deps.manual_registry and deps.manual_registry.count > 0:
                manual_prompt = deps.manual_registry.get_prompt_text(body.message)
                if manual_prompt:
                    system_content += f"\n\n{manual_prompt}"

            model = deps.model_provider.get_model(body.model)
            async for chunk in model.astream(
                [
                    SystemMessage(content=system_content),
                    HumanMessage(content=body.message),
                ]
            ):
                if chunk.content:
                    yield _sse("delta", type="delta", content=chunk.content)
        else:
            # 使用技能
            skills = deps.skill_registry.get_all_skills()
            agent = skill.compose(skills, deps.model_provider) or skill.create_agent(
                deps.model_provider, checkpointer=deps.checkpointer
            )
            query = decision.rewritten_query if decision else body.message

            invoke_cfg = {}
            if body.session_id:
                invoke_cfg["configurable"] = {"thread_id": body.session_id}

            async for event in agent.astream_events(
                {"messages": [HumanMessage(content=query)]},
                version="v2",
                config=invoke_cfg,
            ):
                if (
                    event["event"] == "on_chat_model_stream"
                    and event["data"]["chunk"].content
                ):
                    yield _sse(
                        "delta",
                        type="delta",
                        content=event["data"]["chunk"].content,
                    )

        yield _sse("done", type="done", skill=skill_name)

    return EventSourceResponse(event_generator())


# ── SSE 辅助 ────────────────────────────────────────────────────


def _sse(event: str, **data) -> dict:
    """构建 SSE 事件 dict。"""
    return {
        "event": event,
        "data": json.dumps(data, ensure_ascii=False),
    }
