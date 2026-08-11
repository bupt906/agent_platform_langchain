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
        for skill in deps.declarative_registry.list_skills():
            missing = [name for name in skill.tools if name not in registered_tools]
            runtime_status = None
            if skill.runtime_profile:
                if deps.runtime_manager:
                    runtime_status = deps.runtime_manager.status(skill.runtime_profile)
                else:
                    from agent_platform.runtime.models import RuntimeStatus

                    runtime_status = RuntimeStatus(
                        False,
                        skill.runtime_profile,
                        "unknown",
                        "runtime_manager_unavailable",
                    )
            items.append(
                SkillInfoResponse(
                    name=skill.name,
                    description=skill.description,
                    examples=[],
                    dependencies=[],
                    kind="skill",
                    tools=skill.tools,
                    ready=not missing and (runtime_status is None or runtime_status.ready),
                    missing_tools=missing,
                    runtime_profile=skill.runtime_profile,
                    runtime_backend=runtime_status.backend if runtime_status else None,
                    runtime_reason=runtime_status.reason if runtime_status else None,
                )
            )
        items.extend(
            SkillInfoResponse(
                name=name,
                description="声明式 Skill 配置无效，当前已隔离",
                examples=[],
                dependencies=[],
                kind="skill",
                ready=False,
                unavailable_reason=reason,
            )
            for name, reason in deps.declarative_registry.unavailable_skills.items()
        )
    return SkillListResponse(skills=items, total=len(items))
