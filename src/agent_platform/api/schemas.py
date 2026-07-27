from __future__ import annotations

from pydantic import BaseModel


class ChatRequest(BaseModel):
    message: str
    agent: str | None = None  # 显式指定 Python Agent（agents/ 目录下）
    skill: str | None = None  # 显式指定声明式 Skill（skills/ 目录下）
    model: str | None = None
    session_id: str | None = None
    thinking: bool = False  # 是否启用并流式返回模型思考内容


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

    uuid: str = ""
    task_id: int = 0
    file_path: str
    kb_type_code: str = ""
    kb_ids: list[str]


class ReviewResultItem(BaseModel):
    """单句审阅结果。"""

    sentence_index: int
    reviewed_sentence: str
    has_issue: str = "否"  # "是" | "否"
    content: dict = {}


class ReviewResponse(BaseModel):
    """文档审阅响应。"""

    results: list[ReviewResultItem]


# ── Callback ───────────────────────────────────────────────


class TaskStatusRequest(BaseModel):
    """更新任务状态请求。"""

    taskId: int = 0
    status: str = ""  # "520"=审阅中 "530"=审阅完毕 "777"=失败


class CallbackBatchItem(BaseModel):
    """单条审阅结果（callback 批量提交）。"""

    task_id: int
    sentence_index: int
    reviewed_sentence: str
    has_issue: str = "否"  # "是" | "否"
    content: dict = {}
    error: bool = False


class CallbackBatchRequest(BaseModel):
    """审阅结果批量提交请求：{"results": [...]}。"""

    results: list[CallbackBatchItem]


class CallbackResponse(BaseModel):
    """Callback 通用响应。"""

    code: int = 200
    msg: str = "操作成功"
    data: object = None
