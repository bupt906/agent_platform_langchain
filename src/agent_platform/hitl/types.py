"""Human-in-the-Loop 数据模型。"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4

from pydantic import BaseModel, Field


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    TIMEOUT = "timeout"


class ApprovalRequest(BaseModel):
    """审批请求。"""

    id: str = Field(default_factory=lambda: uuid4().hex[:12])
    session_id: str = ""
    thread_id: str = ""
    node_id: str = ""
    skill_name: str = ""
    operation: str = ""  # "sql_execution" | "contract_decision" | "replan"
    details: str = ""  # 给审批人看的上下文
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    status: ApprovalStatus = ApprovalStatus.PENDING
    decided_by: str | None = None
    decided_at: str | None = None


class ReplanRequest(BaseModel):
    """动态重规划请求。"""

    session_id: str = ""
    thread_id: str = ""
    original_plan_summary: str = ""
    intermediate_results: dict[str, str] = Field(default_factory=dict)
    proposed_revision: str = ""  # LLM 或用户建议的修订


class ApprovalResponse(BaseModel):
    """审批操作响应。"""

    id: str
    status: str
    message: str | None = None
