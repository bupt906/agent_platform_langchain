"""文档审阅 API。"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, HTTPException, Request

from agent_platform.api.schemas import ReviewRequest
from agent_platform.core.deps import PlatformDeps

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/review", tags=["review"])


def _get_deps(request: Request) -> PlatformDeps:
    return request.app.state.deps


# ── 文档审阅 ──────────────────────────────────────────────


@router.post("")
async def review_document(request: Request, body: ReviewRequest) -> dict:
    """对文档执行逐句审阅（异步），结果通过回调 POST /api/callback/batch 返回。

    接口收到请求后立刻返回，审阅在后台执行：
    - 审阅中 → callback 520
    - 审阅完毕 → callback 530 + 结果批量提交
    - 审阅失败 → callback 777
    """
    deps = _get_deps(request)

    if not body.kb_ids:
        raise HTTPException(status_code=400, detail="kb_ids 不能为空")

    if not body.file_path:
        raise HTTPException(status_code=400, detail="file_path 不能为空")

    # 通知审阅中
    await _notify_task_status(deps, body.task_id, "520")

    # 启动后台审阅任务，立刻返回
    asyncio.create_task(_run_review_background(deps, body))

    logger.info("审阅任务已接单: task_id=%d", body.task_id)
    return {"task_id": body.task_id, "uuid": body.uuid, "status": "accepted"}


# ── 后台审阅 ──────────────────────────────────────────────


async def _run_review_background(deps: PlatformDeps, body: ReviewRequest) -> None:
    """后台执行审阅流水线，完成/失败后通过回调通知。"""
    try:
        from agent_platform.agents.document_review.pipeline import run_review_pipeline

        result = await run_review_pipeline(
            file_path=body.file_path,
            kb_ids=body.kb_ids,
            deps=deps,
            task_id=body.task_id,
        )

        results = result.get("results", [])
        if body.uuid:
            for r in results:
                r["uuid"] = body.uuid

        submit_error = None
        if results:
            try:
                await _submit_review_results(deps, results)
            except Exception as e:
                submit_error = str(e)
                logger.error("审阅结果回调失败: %s", e)

        error_count = result.get("summary", {}).get("errors", 0)
        if error_count > 0 or submit_error:
            await _notify_task_status(deps, body.task_id, "777")
        else:
            await _notify_task_status(deps, body.task_id, "530")

    except FileNotFoundError as e:
        logger.warning("审阅文件未找到: %s", e)
        await _notify_task_status(deps, body.task_id, "777")
    except ValueError as e:
        logger.warning("审阅参数错误: %s", e)
        await _notify_task_status(deps, body.task_id, "777")
    except Exception:
        logger.exception("文档审阅失败: task_id=%d", body.task_id)
        await _notify_task_status(deps, body.task_id, "777")


# ── 内部 helper ───────────────────────────────────────────


async def _notify_task_status(deps: PlatformDeps, task_id: int, status: str) -> None:
    try:
        payload = {"taskId": task_id, "status": status}
        url = _callback_url(deps, "/api/callback/task/status")
        if url:
            headers = _callback_headers()
            await deps.http_client.put(url, json=payload, headers=headers, timeout=30.0)
            logger.info("任务状态更新: task_id=%d status=%s", task_id, status)
    except Exception:
        logger.warning("任务状态回调失败", exc_info=True)


async def _submit_review_results(deps: PlatformDeps, results: list[dict]) -> None:
    """提交审阅结果到回调服务。失败时抛出异常，由调用方决定任务状态。"""
    if not results:
        return
    items = [
        {
            "task_id": r.get("task_id", 0),
            "sentence_index": r.get("sentence_index", 0),
            "reviewed_sentence": r.get("reviewed_sentence", ""),
            "has_issue": r.get("has_issue", "否"),
            "content": r.get("content", {}),
            "error": r.get("error", False),
        }
        for r in results
    ]
    url = _callback_url(deps, "/api/callback/batch")
    if not url:
        return
    payload = {"results": items}
    headers = _callback_headers()
    resp = await deps.http_client.post(url, json=payload, headers=headers, timeout=30.0)
    resp.raise_for_status()
    logger.info("审阅结果回调: %d 条", len(items))


def _callback_headers() -> dict:
    from agent_platform.config.settings import settings
    token = settings.callback_auth_token
    if token:
        return {"X-Auth-Token": token}
    return {}


def _callback_url(deps: PlatformDeps, path: str) -> str:
    from agent_platform.config.settings import settings
    base = settings.callback_base_url.strip()
    if not base:
        return ""  # 未配置回调地址 → 禁用回调
    return f"{base}{path}"
