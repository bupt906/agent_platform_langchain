"""审计日志数据模型。"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from pydantic import BaseModel, Field


class AuditRecord(BaseModel):
    """单次 Agent 调用的完整审计记录。"""

    id: str = Field(default_factory=lambda: uuid4().hex[:12])
    session_id: str | None = None
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    agent_type: str = ""  # "router" | "skill:qa" | "multi" | "general"
    user_message: str = ""
    assistant_message: str = ""
    model_used: str = ""
    tokens_prompt: int = 0
    tokens_completion: int = 0
    tokens_total: int = 0
    duration_ms: float = 0.0
    skill_used: str | None = None
    router_confidence: float | None = None
    error: str | None = None


class ToolCallRecord(BaseModel):
    """单次工具调用的审计记录。"""

    id: str = Field(default_factory=lambda: uuid4().hex[:12])
    audit_id: str = ""  # 关联的 AuditRecord.id
    tool_name: str = ""
    start_time: float = 0.0
    end_time: float = 0.0
    duration_ms: float = 0.0
    input_args: str = ""  # JSON
    output_summary: str = ""
    success: bool = True


class AuditQueryRequest(BaseModel):
    """审计日志查询参数。"""

    session_id: str | None = None
    skill: str | None = None
    start_time: str | None = None
    end_time: str | None = None
    limit: int = 100
    offset: int = 0


class AuditStats(BaseModel):
    """审计统计汇总。"""

    total_calls: int = 0
    total_tokens: int = 0
    total_duration_ms: float = 0.0
    avg_duration_ms: float = 0.0
    by_skill: dict[str, int] = Field(default_factory=dict)
    errors: int = 0
