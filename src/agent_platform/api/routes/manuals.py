"""技能手册 API 端点。"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from agent_platform.core.deps import PlatformDeps
from agent_platform.skill_manuals.loader import SkillManual

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/skill-manuals", tags=["skill-manuals"])


def _get_deps(request: Request) -> PlatformDeps:
    return request.app.state.deps


# ── 列表 ──

@router.get("")
async def list_manuals(request: Request) -> dict:
    deps = _get_deps(request)
    if not deps.manual_registry:
        return {"manuals": [], "total": 0}

    infos = deps.manual_registry.list_infos()
    return {"manuals": infos, "total": len(infos)}


# ── 详情 ──

@router.get("/{name}")
async def get_manual(request: Request, name: str) -> dict:
    deps = _get_deps(request)
    if not deps.manual_registry:
        raise HTTPException(status_code=404, detail="手册系统未启用")

    manual = deps.manual_registry.get(name)
    if not manual:
        raise HTTPException(status_code=404, detail=f"未找到手册: {name}")

    return {
        "name": manual.name,
        "description": manual.description,
        "keywords": manual.keywords,
        "content": manual.content,
    }


# ── 注册 / 更新 ──

class ManualBody(BaseModel):
    name: str
    description: str = ""
    keywords: list[str] = []
    content: str = ""


@router.put("/{name}", status_code=201)
async def upsert_manual(request: Request, name: str, body: ManualBody) -> dict:
    deps = _get_deps(request)
    if not deps.manual_registry:
        raise HTTPException(status_code=503, detail="手册系统未启用")

    manual = SkillManual(
        name=body.name or name,
        description=body.description,
        keywords=body.keywords,
        content=body.content,
        source_path="api",
    )
    deps.manual_registry.register(manual)
    logger.info("已注册技能手册: %s (%d 个关键词)", manual.name, len(manual.keywords))
    return {"status": "ok", "name": manual.name}


# ── 删除 ──

@router.delete("/{name}")
async def delete_manual(request: Request, name: str) -> dict:
    deps = _get_deps(request)
    if not deps.manual_registry:
        raise HTTPException(status_code=503, detail="手册系统未启用")

    if deps.manual_registry.unregister(name):
        logger.info("已删除技能手册: %s", name)
        return {"status": "deleted", "name": name}
    raise HTTPException(status_code=404, detail=f"未找到手册: {name}")


# ── 重载 ──

@router.post("/reload")
async def reload_manuals(request: Request) -> dict:
    deps = _get_deps(request)
    if not deps.manual_registry:
        raise HTTPException(status_code=503, detail="手册系统未启用")

    # 从原目录重新加载
    from agent_platform.config.settings import settings

    manuals_dir = settings.skill_manual_path
    if not Path(manuals_dir).is_absolute():
        package_dir = Path(__file__).parent.parent.parent  # src/agent_platform/
        manuals_dir = str(package_dir / manuals_dir)

    count = deps.manual_registry.load_from_dir(manuals_dir)
    return {"status": "reloaded", "count": count, "total": deps.manual_registry.count}
