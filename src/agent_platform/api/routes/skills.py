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
    items = [
        SkillInfoResponse(
            name=s.name,
            description=s.description,
            examples=s.examples,
            dependencies=s.dependencies,
        )
        for s in deps.skill_registry.list_skills()
    ]

    # 合并声明式 Skill（skills/ 目录下的 SKILL.md），前端下拉菜单才能
    # 选择它们。声明式 skill 无 examples，用 tools 补充展示。
    if deps.declarative_registry:
        for d in deps.declarative_registry.list_skills():
            items.append(
                SkillInfoResponse(
                    name=d.name,
                    description=d.description,
                    examples=[f"tools: {', '.join(d.tools)}"],
                    dependencies=[],
                )
            )

    return SkillListResponse(skills=items, total=len(items))
