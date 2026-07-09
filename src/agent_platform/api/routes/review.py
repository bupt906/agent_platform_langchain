"""文档审阅 API 端点。

POST /review — 对文档执行逐句审阅，基于知识库标准输出结构化结果。
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request

from agent_platform.agents.document_review.pipeline import run_review_pipeline
from agent_platform.api.schemas import ReviewRequest, ReviewResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/review", tags=["review"])


def _get_deps(request: Request):
    return request.app.state.deps


@router.post("", response_model=ReviewResponse)
async def review_document(request: Request, body: ReviewRequest):
    """对文档进行逐句审阅。

    流程：解析文档 → 句子切分 → 逐句在知识库中检索比对 → 输出结构化审查结果。

    请求体：
    ```json
    {
      "file_path": "/path/to/document.docx",
      "kb_ids": ["compliance", "terminology"]
    }
    ```

    返回每个句子的审查结论，包含是否有问题、错误原因、修改建议、建议依据。
    """
    deps = _get_deps(request)

    if not body.kb_ids:
        raise HTTPException(status_code=400, detail="kb_ids 不能为空，至少指定一个知识库")

    # 验证知识库 ID 有效性
    if deps.kb_registry:
        invalid = [k for k in body.kb_ids if not deps.kb_registry.get(k)]
        if invalid:
            available = [k.kb_id for k in deps.kb_registry.list_all()]
            raise HTTPException(
                status_code=400,
                detail=f"无效的知识库 ID: {invalid}，可用: {available}",
            )

    # 设置 skill 的 deps 引用
    import agent_platform.agents.document_review.skill as skill_mod

    skill_mod._skill_deps = deps

    try:
        result = await run_review_pipeline(body.file_path, body.kb_ids, deps)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("文档审阅失败: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"审阅失败: {e}")

    return ReviewResponse(**result)


@router.get("/kbs")
async def list_knowledge_bases(request: Request):
    """列出所有可用的审查知识库。"""
    deps = _get_deps(request)
    if not deps.kb_registry:
        return {"knowledge_bases": [], "total": 0}

    infos = deps.kb_registry.list_infos()
    return {"knowledge_bases": infos, "total": len(infos)}
