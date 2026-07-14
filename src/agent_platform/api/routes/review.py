"""文档审阅 API。"""

from __future__ import annotations

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
    """对文档执行逐句审阅，结果通过回调 POST /api/callback/batch 返回。"""
    deps = _get_deps(request)

    if not body.kb_ids:
        raise HTTPException(status_code=400, detail="kb_ids 不能为空")

    if deps.kb_registry:
        available = [kb.kb_id for kb in deps.kb_registry.list_all()]
        invalid = [k for k in body.kb_ids if k not in available]
        if invalid:
            raise HTTPException(
                status_code=400,
                detail=f"无效的知识库 ID: {invalid}。可用: {available}",
            )

    # 通知审阅中
    await _notify_task_status(deps, body.task_id, "1")

    try:
        from agent_platform.agents.document_review.pipeline import run_review_pipeline

        result = await run_review_pipeline(
            file_path=body.file_path,
            kb_ids=body.kb_ids,
            deps=deps,
            task_id=body.task_id,
        )

        results = result.get("results", [])
        # uuid 透传到每条结果
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
            await _notify_task_status(deps, body.task_id, "3")
        else:
            await _notify_task_status(deps, body.task_id, "2")

        return {"task_id": body.task_id, "uuid": body.uuid, "status": "ok"}

    except FileNotFoundError as e:
        await _notify_task_status(deps, body.task_id, "3")
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        await _notify_task_status(deps, body.task_id, "3")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("文档审阅失败")
        await _notify_task_status(deps, body.task_id, "3")
        raise HTTPException(status_code=500, detail=f"审阅失败: {e}")


# ── 知识库列表 ────────────────────────────────────────────


@router.get("/kbs")
async def list_knowledge_bases(request: Request) -> dict:
    deps = _get_deps(request)
    if not deps.kb_registry:
        return {"knowledge_bases": [], "total": 0}
    infos = deps.kb_registry.list_infos()
    return {"knowledge_bases": infos, "total": len(infos)}


# ── 内部 helper ───────────────────────────────────────────


async def _notify_task_status(deps: PlatformDeps, task_id: int, status: str) -> None:
    try:
        payload = {"task_id": task_id, "status": status}
        url = _callback_url(deps, "/api/callback/task/status")
        if url:
            headers = _callback_headers()
            await deps.http_client.put(url, json=payload, headers=headers)
            logger.info("任务状态更新: task_id=%d status=%s", task_id, status)
    except Exception:
        logger.warning("任务状态回调失败", exc_info=True)


async def _submit_review_results(deps: PlatformDeps, results: list[dict]) -> None:
    if not results:
        return
    try:
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
        if url:
            payload = {"results": items}
            headers = _callback_headers()
            await deps.http_client.post(url, json=payload, headers=headers)
            logger.info("审阅结果回调: %d 条", len(items))
    except Exception:
        logger.warning("审阅结果回调失败", exc_info=True)


def _callback_headers() -> dict:
    from agent_platform.config.settings import settings
    token = settings.callback_auth_token
    if token:
        return {"X-Auth-Token": token}
    return {}


def _callback_url(deps: PlatformDeps, path: str) -> str | None:
    from agent_platform.config.settings import settings
    base = settings.callback_base_url
    if not base:
        logger.debug("callback_base_url 未配置，跳过回调: %s", path)
        return None
    return f"{base}{path}"
