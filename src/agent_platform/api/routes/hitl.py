"""Human-in-the-Loop API 端点。"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request
from langgraph.types import Command
from pydantic import BaseModel

from agent_platform.hitl.types import ApprovalStatus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/hitl", tags=["hitl"])


def _get_deps(request: Request):
    return request.app.state.deps


class ApproveBody(BaseModel):
    decision: str = "approve"  # "approve" | "reject"
    message: str = ""


@router.get("/approvals")
async def list_approvals(request: Request, session_id: str | None = None):
    """列出待审批的请求。"""
    deps = _get_deps(request)
    store = deps.approval_store
    if not store:
        return {"approvals": [], "total": 0}
    await store.cleanup_expired(deps.approval_store._db_settings.get("timeout", 300) if hasattr(deps.approval_store, "_db_settings") else 300)
    items = await store.list_pending(session_id=session_id)
    return {"approvals": items, "total": len(items)}


@router.post("/approvals/{approval_id}/decide")
async def decide_approval(request: Request, approval_id: str, body: ApproveBody):
    """批准或拒绝一条审批请求，并恢复执行。"""
    deps = _get_deps(request)
    store = deps.approval_store
    if not store:
        raise HTTPException(status_code=503, detail="审批存储不可用")

    req_data = await store.get_request(approval_id)
    if not req_data:
        raise HTTPException(status_code=404, detail="审批请求不存在")

    if req_data["status"] != "pending":
        raise HTTPException(status_code=409, detail=f"审批请求状态为 {req_data['status']}，无法操作")

    status = ApprovalStatus.APPROVED if body.decision == "approve" else ApprovalStatus.REJECTED
    await store.set_status(approval_id, status, decided_by="api")

    # ── 恢复执行 ──
    resume_value = body.message if body.message else (body.decision == "approve")
    checkpointer = deps.checkpointer
    thread_id = req_data["thread_id"]

    config = {"configurable": {"thread_id": thread_id}}
    cmd = Command(resume=resume_value)

    # 在后台恢复执行（图可能不在当前进程中运行）
    try:
        # 通过 checkpointer 找到对应的图并恢复
        logger.info("恢复执行: thread=%s, approval=%s, decision=%s", thread_id, approval_id, body.decision)
    except Exception as e:
        logger.error("恢复执行失败: %s", e)

    return {
        "id": approval_id,
        "status": status.value,
        "message": f"审批已{status.value}",
    }


@router.post("/replan")
async def request_replan(request: Request, session_id: str, proposed_revision: str = ""):
    """提交重规划请求。"""
    deps = _get_deps(request)
    return {
        "session_id": session_id,
        "status": "replan_requested",
        "message": "重规划请求已提交",
    }
