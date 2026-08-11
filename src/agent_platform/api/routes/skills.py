from __future__ import annotations

import shutil
from typing import Any

from fastapi import APIRouter, Request

from agent_platform.api.schemas import SkillInfoResponse, SkillListResponse
from agent_platform.core.deps import PlatformDeps
from agent_platform.tools.registry import tool_map

router = APIRouter()


def _get_deps(request: Request) -> PlatformDeps:
    return request.app.state.deps


def _agentcad_available() -> bool:
    """检测 agentcad CLI 是否可用（PATH 或常见安装位置）。"""
    if shutil.which("agentcad"):
        return True
    from pathlib import Path
    candidates = [
        Path("/opt/anaconda3/envs/agentcad-py312/bin/agentcad"),
        Path("/opt/miniconda3/envs/agentcad-py312/bin/agentcad"),
    ]
    return any(p.exists() for p in candidates)


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
            # cad-agentcad 依赖外部 agentcad CLI，额外检测它是否真的安装了
            if skill.name == "cad-agentcad" and not _agentcad_available():
                missing.append("agentcad")
            items.append(
                SkillInfoResponse(
                    name=skill.name,
                    description=skill.description,
                    examples=[],
                    dependencies=[],
                    kind="skill",
                    tools=skill.tools,
                    ready=not missing,
                    missing_tools=missing,
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
