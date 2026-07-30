"""审计日志 API 端点。"""

from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter(prefix="/audit", tags=["audit"])


def _get_audit_store(request: Request):
    deps = request.app.state.deps
    return deps.audit_store


@router.get("")
async def list_audit_records(
    request: Request,
    session_id: str | None = None,
    skill: str | None = None,
    skill_used: str | None = None,
    limit: int = 100,
    offset: int = 0,
):
    """查询审计日志。"""
    store = _get_audit_store(request)
    if not store:
        return {"records": [], "total": 0}
    skill_filter = skill or skill_used  # 兼容前端两种参数名
    records, total = await store.query_with_count(session_id=session_id, skill=skill_filter, limit=limit, offset=offset)
    return {"records": records, "total": total}


@router.get("/stats")
async def get_audit_stats(request: Request, days: int = 30):
    """获取审计统计汇总。"""
    store = _get_audit_store(request)
    if not store:
        return {"error": "audit store not available"}
    stats = await store.aggregate_stats(days=days)
    return stats.model_dump()


@router.get("/{audit_id}/tools")
async def get_tool_calls(request: Request, audit_id: str):
    """获取某次调用的工具调用详情。"""
    store = _get_audit_store(request)
    if not store:
        return {"tool_calls": []}
    calls = await store.query_tool_calls(audit_id)
    return {"audit_id": audit_id, "tool_calls": calls}
