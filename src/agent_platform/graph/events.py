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
