"""Callback 接口 — 任务状态更新 + 审阅结果批量提交。"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request

from agent_platform.api.schemas import CallbackBatchItem, CallbackResponse, TaskStatusRequest

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/callback", tags=["callback"])

# ── 内存存储（生产环境应替换为持久化存储） ──────────────

_task_statuses: dict[int, str] = {}
_review_results: dict[int, list[dict]] = {}


@router.put("/task/status", response_model=CallbackResponse)
async def update_task_status(request: Request, body: TaskStatusRequest) -> CallbackResponse:
    """更新任务状态。

    status: "1"=审阅中 "2"=审阅完毕 "3"=失败
    """
    _task_statuses[body.taskId] = body.status
    logger.info("任务状态更新: taskId=%d status=%s", body.taskId, body.status)
    return CallbackResponse(code=200, msg="操作成功", data=True)


@router.post("/batch", response_model=CallbackResponse)
async def submit_batch_results(request: Request, body: list[CallbackBatchItem]) -> CallbackResponse:
    """批量提交审阅结果。"""
    task_id = body[0].task_id if body else 0
    _review_results.setdefault(task_id, []).extend(
        [item.model_dump() for item in body]
    )
    logger.info("审阅结果提交: task_id=%d count=%d", task_id, len(body))
    return CallbackResponse(code=200, msg="操作成功", data=len(body))


@router.get("/task/status/{task_id}")
async def get_task_status(request: Request, task_id: int) -> CallbackResponse:
    """查询任务状态。"""
    status = _task_statuses.get(task_id)
    if status is None:
        return CallbackResponse(code=404, msg="任务不存在", data=None)
    return CallbackResponse(code=200, msg="操作成功", data={"taskId": task_id, "status": status})


@router.get("/batch/{task_id}")
async def get_review_results(request: Request, task_id: int) -> CallbackResponse:
    """查询审阅结果。"""
    results = _review_results.get(task_id, [])
    return CallbackResponse(code=200, msg="操作成功", data={"task_id": task_id, "results": results, "total": len(results)})
