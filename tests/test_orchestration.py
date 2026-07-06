from __future__ import annotations

import asyncio
import json

import pytest

from agent_platform.graph.events import (
    PlanEvent,
    StepDoneEvent,
    StepStartEvent,
    SynthesisDeltaEvent,
    SynthesisStartEvent,
)
from agent_platform.graph.patterns import ExecutionPlan, SubTask


class TestEventSerialization:
    def test_step_start_event_to_dict(self):
        event = StepStartEvent(
            step_id="s1", skill_name="qa", description="测试"
        )
        d = event.to_dict()
        assert d["type"] == "step_start"
        assert d["step_id"] == "s1"
        assert "timestamp" in d

    def test_plan_event_to_dict(self):
        event = PlanEvent(subtasks=[{"id": "s1", "skill_name": "qa"}])
        d = event.to_dict()
        assert d["type"] == "plan"
        assert len(d["subtasks"]) == 1

    def test_event_json_roundtrip(self):
        event = StepDoneEvent(
            step_id="s1", skill_name="qa", result_summary="结果摘要"
        )
        d = event.to_dict()
        json_str = json.dumps(d, ensure_ascii=False)
        parsed = json.loads(json_str)
        assert parsed["step_id"] == "s1"
        assert parsed["result_summary"] == "结果摘要"

    def test_synthesis_events(self):
        start = SynthesisStartEvent()
        assert start.type == "synthesis_start"

        delta = SynthesisDeltaEvent(content="分析中...")
        d = delta.to_dict()
        assert d["content"] == "分析中..."


class TestExecutionPlan:
    def test_sequential_plan_creation(self):
        plan = ExecutionPlan(
            mode="sequential",
            subtasks=[
                SubTask(id="s1", skill_name="data_query", description="查询数据"),
                SubTask(
                    id="s2",
                    skill_name="contract_review",
                    description="审查合同",
                    depends_on=["s1"],
                ),
            ],
        )
        assert plan.mode == "sequential"
        assert len(plan.subtasks) == 2
        assert plan.subtasks[1].depends_on == ["s1"]

    def test_parallel_plan_creation(self):
        plan = ExecutionPlan(
            mode="parallel",
            subtasks=[
                SubTask(id="s1", skill_name="qa", description="知识检索"),
                SubTask(id="s2", skill_name="data_query", description="数据查询"),
            ],
        )
        assert plan.mode == "parallel"
        assert len(plan.subtasks) == 2

    def test_subtask_model_dump(self):
        st = SubTask(id="s1", skill_name="qa", description="测试")
        d = st.model_dump()
        assert d["id"] == "s1"
        assert d["skill_name"] == "qa"
        assert d["depends_on"] == []
