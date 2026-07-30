from __future__ import annotations

from fastapi import APIRouter, Request

from agent_platform.api.schemas import SkillInfoResponse, SkillListResponse
from agent_platform.core.deps import PlatformDeps
from agent_platform.tools.registry import tool_map

router = APIRouter()


def _get_deps(request: Request) -> PlatformDeps:
    return request.app.state.deps


@router.get("/skills", response_model=SkillListResponse)
async def list_skills(request: Request) -> SkillListResponse:
    deps = _get_deps(request)
    skills = deps.skill_registry.list_skills()
    items = [
        SkillInfoResponse(
            name=s.name,
            description=s.description,
            examples=s.examples,
            dependencies=s.dependencies,
            kind="agent",
        )
        for s in skills
    ]
    if deps.declarative_registry:
        registered_tools = tool_map()
        items.extend(
            SkillInfoResponse(
                name=skill.name,
                description=skill.description,
                examples=[],
                dependencies=[],
                kind="skill",
                tools=skill.tools,
                ready=all(name in registered_tools for name in skill.tools),
                missing_tools=[name for name in skill.tools if name not in registered_tools],
            )
            for skill in deps.declarative_registry.list_skills()
        )
    return SkillListResponse(skills=items, total=len(items))
