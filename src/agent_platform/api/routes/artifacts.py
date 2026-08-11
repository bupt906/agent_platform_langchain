from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

router = APIRouter(prefix="/artifacts", tags=["artifacts"])


@router.get("/{artifact_id}")
async def get_artifact(request: Request, artifact_id: str) -> FileResponse:
    """按不可猜测 ID 返回已发布产物，不接受任意本地路径。"""
    store = request.app.state.deps.artifact_store
    record = store.get(artifact_id) if store else None
    if not record:
        raise HTTPException(status_code=404, detail="产物不存在或已过期")

    headers = {
        "Cache-Control": "private, no-store",
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "no-referrer",
    }
    if record.media_type == "text/html":
        # HTML 仅用于受限 iframe 预览。禁止联网、表单、导航和父页面访问。
        headers["Content-Security-Policy"] = (
            "sandbox allow-scripts; default-src 'none'; "
            "script-src 'unsafe-inline' 'unsafe-eval'; style-src 'unsafe-inline'; "
            "img-src data: blob:; worker-src blob:; connect-src 'none'; "
            "font-src data:; media-src data: blob:"
        )
    return FileResponse(record.path, media_type=record.media_type, headers=headers)
