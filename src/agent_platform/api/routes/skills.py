from __future__ import annotations

from fastapi import APIRouter, Request

from agent_platform.api.schemas import SkillInfoResponse, SkillListResponse
from agent_platform.core.deps import PlatformDeps

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
        )
        for s in skills
    ]
    return SkillListResponse(skills=items, total=len(items))
