"""Callback 接口 — 任务状态更新 + 审阅结果批量提交。"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request

from agent_platform.api.schemas import CallbackBatchRequest, CallbackResponse, TaskStatusRequest

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/callback", tags=["callback"])

# ── 内存存储（生产环境应替换为持久化存储） ──────────────

_task_statuses: dict[int, str] = {}
_review_results: dict[int, list[dict]] = {}

_MAX_ENTRIES = 10_000  # 防止无限制内存增长


def _cleanup_oldest(store: dict, max_entries: int = _MAX_ENTRIES) -> None:
    """当字典条目超限时删除最早插入的条目。"""
    if len(store) > max_entries:
        # 按插入顺序删除最早的条目（Python 3.7+ dict 保持插入顺序）
        excess = len(store) - max_entries
        keys_to_remove = list(store.keys())[:excess]
        for k in keys_to_remove:
            del store[k]


@router.put("/task/status", response_model=CallbackResponse)
async def update_task_status(request: Request, body: TaskStatusRequest) -> CallbackResponse:
    """更新任务状态。

    status: "1"=审阅中 "2"=审阅完毕 "3"=失败
    """
    _task_statuses[body.taskId] = body.status
    _cleanup_oldest(_task_statuses)
    logger.info("任务状态更新: taskId=%d status=%s", body.taskId, body.status)
    return CallbackResponse(code=200, msg="操作成功", data=True)


@router.post("/batch", response_model=CallbackResponse)
async def submit_batch_results(request: Request, body: CallbackBatchRequest) -> CallbackResponse:
    """批量提交审阅结果。请求体为 {"results": [...]}。"""
    items = body.results
    task_id = items[0].task_id if items else 0
    _review_results.setdefault(task_id, []).extend(
        [item.model_dump() for item in items]
    )
    _cleanup_oldest(_review_results)
    logger.info("审阅结果提交: task_id=%d count=%d", task_id, len(items))
    return CallbackResponse(code=200, msg="操作成功", data=len(items))


@router.get("/task/status/{task_id}")
async def get_task_status(request: Request, task_id: int) -> CallbackResponse:
    """查询任务状态。"""
    status = _task_statuses.get(task_id)
    if status is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return CallbackResponse(code=200, msg="操作成功", data={"taskId": task_id, "status": status})


@router.get("/batch/{task_id}")
async def get_review_results(request: Request, task_id: int) -> CallbackResponse:
    """查询审阅结果。"""
    results = _review_results.get(task_id, [])
    return CallbackResponse(code=200, msg="操作成功", data={"task_id": task_id, "results": results, "total": len(results)})
