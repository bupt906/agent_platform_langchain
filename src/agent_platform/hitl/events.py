"""HITL 相关的 SSE 事件类型。"""

from __future__ import annotations

from dataclasses import dataclass, field

from agent_platform.graph.events import OrchestrationEvent


@dataclass
class ApprovalNeededEvent(OrchestrationEvent):
    """需要人工审批时发送的 SSE 事件。"""

    type: str = "approval_needed"
    approval_id: str = ""
    operation: str = ""
    skill_name: str = ""
    details: str = ""


@dataclass
class ApprovalResultEvent(OrchestrationEvent):
    """审批结果事件。"""

    type: str = "approval_result"
    approval_id: str = ""
    status: str = ""
    message: str = ""


@dataclass
class ReplanEvent(OrchestrationEvent):
    """动态重规划事件。"""

    type: str = "replan"
    reason: str = ""
    new_plan_summary: str = ""
