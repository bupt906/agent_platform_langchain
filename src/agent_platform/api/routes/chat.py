from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Request
from langchain_core.messages import HumanMessage, SystemMessage
from sse_starlette.sse import EventSourceResponse

from agent_platform.api.schemas import ChatRequest, ChatResponse
from agent_platform.core.deps import PlatformDeps
from agent_platform.core.router import RouterDecision, _build_router_prompt
from agent_platform.graph.orchestration import OrchestrationEngine
from agent_platform.graph.patterns import ExecutionPlan

logger = logging.getLogger(__name__)

router = APIRouter()


def _get_deps(request: Request) -> PlatformDeps:
    return request.app.state.deps


@router.post("/chat", response_model=ChatResponse)
async def chat(request: Request, body: ChatRequest) -> ChatResponse:
    deps = _get_deps(request)

    if body.skill:
        skill = deps.skill_registry.get(body.skill)
        if not skill:
            return ChatResponse(
                reply=f"未找到技能: {body.skill}", skill_used="error"
            )
        all_skills = {
            s.name: deps.skill_registry.get(s.name)
            for s in deps.skill_registry.list_skills()
        }
        all_skills = {k: v for k, v in all_skills.items() if v is not None}
        agent = skill.compose(all_skills, deps.model_provider) or skill.create_agent(
            deps.model_provider
        )
        result = await agent.ainvoke(
            {"messages": [HumanMessage(content=body.message)]}
        )
        return ChatResponse(
            reply=result["messages"][-1].content,
            skill_used=skill.name,
        )

    model = deps.model_provider.get_model(body.model)
    structured_model = model.with_structured_output(RouterDecision)
    system_prompt = _build_router_prompt(deps)
    decision: RouterDecision = await structured_model.ainvoke(
        [SystemMessage(content=system_prompt), HumanMessage(content=body.message)]
    )

    if decision.mode == "multi" and decision.execution_plan:
        engine = OrchestrationEngine(deps)
        result_text = await engine.execute(body.message, decision.execution_plan)
        return ChatResponse(reply=result_text, skill_used="multi_agent")

    skill = deps.skill_registry.get(decision.skill_name)
    if skill:
        all_skills = {
            s.name: deps.skill_registry.get(s.name)
            for s in deps.skill_registry.list_skills()
        }
        all_skills = {k: v for k, v in all_skills.items() if v is not None}
        agent = skill.compose(all_skills, deps.model_provider) or skill.create_agent(
            deps.model_provider
        )
        result = await agent.ainvoke(
            {"messages": [HumanMessage(content=decision.rewritten_query)]}
        )
        return ChatResponse(
            reply=result["messages"][-1].content,
            skill_used=decision.skill_name,
        )

    general_model = deps.model_provider.get_model(body.model)
    response = await general_model.ainvoke(
        [
            SystemMessage(content="你是一个通用智能助手，尽力回答用户的问题。"),
            HumanMessage(content=body.message),
        ]
    )
    return ChatResponse(reply=response.content, skill_used="general")


@router.post("/chat/stream")
async def chat_stream(request: Request, body: ChatRequest) -> EventSourceResponse:
    deps = _get_deps(request)

    async def event_generator():
        if body.skill:
            skill_name = body.skill
            decision = None
        else:
            model = deps.model_provider.get_model(body.model)
            structured_model = model.with_structured_output(RouterDecision)
            system_prompt = _build_router_prompt(deps)
            decision = await structured_model.ainvoke(
                [
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=body.message),
                ]
            )
            skill_name = decision.skill_name
            yield {
                "event": "routing",
                "data": json.dumps(
                    {
                        "type": "routing",
                        "skill": skill_name,
                        "mode": decision.mode,
                        "confidence": decision.confidence,
                    },
                    ensure_ascii=False,
                ),
            }

        is_multi = decision and decision.mode == "multi" and decision.execution_plan
        if is_multi:
            plan = decision.execution_plan
            yield {
                "event": "plan",
                "data": json.dumps(
                    {
                        "type": "plan",
                        "mode": plan.mode,
                        "subtasks": [s.model_dump() for s in plan.subtasks],
                    },
                    ensure_ascii=False,
                ),
            }
            engine = OrchestrationEngine(deps)
            async for event in engine.execute_stream(body.message, plan):
                yield {
                    "event": event.type,
                    "data": json.dumps(event.to_dict(), ensure_ascii=False),
                }
            yield {
                "event": "done",
                "data": json.dumps(
                    {"type": "done", "skill": "multi_agent"}, ensure_ascii=False
                ),
            }
        else:
            skill = deps.skill_registry.get(skill_name)
            if not skill:
                model = deps.model_provider.get_model(body.model)
                async for chunk in model.astream(
                    [
                        SystemMessage(
                            content="你是一个通用智能助手，尽力回答用户的问题。"
                        ),
                        HumanMessage(content=body.message),
                    ]
                ):
                    if chunk.content:
                        yield {
                            "event": "delta",
                            "data": json.dumps(
                                {"type": "delta", "content": chunk.content},
                                ensure_ascii=False,
                            ),
                        }
            else:
                all_skills = {
                    s.name: deps.skill_registry.get(s.name)
                    for s in deps.skill_registry.list_skills()
                }
                all_skills = {k: v for k, v in all_skills.items() if v is not None}
                agent = skill.compose(
                    all_skills, deps.model_provider
                ) or skill.create_agent(deps.model_provider)
                query = (
                    decision.rewritten_query if decision else body.message
                )
                async for event in agent.astream_events(
                    {"messages": [HumanMessage(content=query)]},
                    version="v2",
                ):
                    if (
                        event["event"] == "on_chat_model_stream"
                        and event["data"]["chunk"].content
                    ):
                        yield {
                            "event": "delta",
                            "data": json.dumps(
                                {
                                    "type": "delta",
                                    "content": event["data"]["chunk"].content,
                                },
                                ensure_ascii=False,
                            ),
                        }

            yield {
                "event": "done",
                "data": json.dumps(
                    {"type": "done", "skill": skill_name}, ensure_ascii=False
                ),
            }

    return EventSourceResponse(event_generator())
