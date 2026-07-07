from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class OrchestrationEvent:
    type: str = ""
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if v is not None}


@dataclass
class PlanEvent(OrchestrationEvent):
    type: str = "plan"
    subtasks: list[dict[str, str]] = field(default_factory=list)


@dataclass
class StepStartEvent(OrchestrationEvent):
    type: str = "step_start"
    step_id: str = ""
    skill_name: str = ""
    description: str = ""


@dataclass
class StepDeltaEvent(OrchestrationEvent):
    type: str = "step_delta"
    step_id: str = ""
    content: str = ""


@dataclass
class StepDoneEvent(OrchestrationEvent):
    type: str = "step_done"
    step_id: str = ""
    skill_name: str = ""
    result_summary: str = ""


@dataclass
class SynthesisStartEvent(OrchestrationEvent):
    type: str = "synthesis_start"


@dataclass
class SynthesisDeltaEvent(OrchestrationEvent):
    type: str = "synthesis_delta"
    content: str = ""


# ── HITL 事件 ──────────────────────────────────────────────


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
