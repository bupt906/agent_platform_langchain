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
    approval_timeout = request.app.state.settings.hitl_approval_timeout if hasattr(request.app.state, "settings") else 300
    await store.cleanup_expired(approval_timeout)
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
    thread_id = req_data["thread_id"]
    skill_name = req_data.get("skill_name", "")

    config = {"configurable": {"thread_id": thread_id}}
    cmd = Command(resume=resume_value)

    # 重建 skill 的 agent graph 并通过 Command 恢复执行
    try:
        skill = deps.skill_registry.get(skill_name) if skill_name else None
        if skill:
            skills = deps.skill_registry.get_all_skills()
            agent = skill.compose(skills, deps.model_provider) or skill.create_agent(
                deps.model_provider, checkpointer=deps.checkpointer
            )
            # 使用 Command 恢复被 interrupt() 暂停的图执行
            await agent.ainvoke(cmd, config=config)
            logger.info("恢复执行成功: thread=%s, approval=%s, decision=%s", thread_id, approval_id, body.decision)
        else:
            logger.warning("无法恢复执行: 未找到 skill '%s'", skill_name)
    except Exception as e:
        logger.error("恢复执行失败: %s", e)
        raise HTTPException(status_code=500, detail=f"恢复执行失败: {e}") from e

    return {
        "id": approval_id,
        "status": status.value,
        "message": f"审批已{status.value}",
    }


@router.post("/replan")
async def request_replan(request: Request, session_id: str, proposed_revision: str = ""):
    """提交重规划请求。"""
    _ = _get_deps(request)  # 预留：后续可用于校验 session 与审批状态
    return {
        "session_id": session_id,
        "status": "replan_requested",
        "message": "重规划请求已提交",
    }
