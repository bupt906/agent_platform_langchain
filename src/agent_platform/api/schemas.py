from __future__ import annotations

from pydantic import BaseModel


class ChatRequest(BaseModel):
    message: str
    skill: str | None = None
    model: str | None = None
    session_id: str | None = None


class ChatResponse(BaseModel):
    reply: str
    skill_used: str
    model_used: str = ""
    session_id: str | None = None
    approval_required: bool = False
    approval_id: str | None = None


class SkillInfoResponse(BaseModel):
    name: str
    description: str
    examples: list[str]
    dependencies: list[str] = []


class SkillListResponse(BaseModel):
    skills: list[SkillInfoResponse]
    total: int


class SubTaskResponse(BaseModel):
    id: str
    skill_name: str
    description: str
    status: str = "pending"


# ── 文档审阅 ──────────────────────────────────────────────


class ReviewRequest(BaseModel):
    """文档审阅请求。"""

    file_path: str
    kb_ids: list[str]


class ReviewResultItem(BaseModel):
    """单句审阅结果。"""

    已审阅的句子: str
    是否有问题: str  # "是" | "否"
    content: dict = {}


class ReviewResponse(BaseModel):
    """文档审阅响应。"""

    results: list[ReviewResultItem]
    summary: dict
