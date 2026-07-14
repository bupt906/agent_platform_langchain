from __future__ import annotations

import pytest
from pydantic import ValidationError

from agent_platform.core.router import RouterDecision
from agent_platform.graph.patterns import ExecutionPlan, SubTask


class TestRouterDecisionBackwardCompat:
    def test_single_mode_defaults(self):
        decision = RouterDecision(
            skill_name="document_review",
            rewritten_query="test",
            confidence=0.8,
        )
        assert decision.mode == "single"
        assert decision.execution_plan is None

    def test_confidence_bounds(self):
        RouterDecision(
            skill_name="document_review", rewritten_query="test", confidence=0.0
        )
        RouterDecision(
            skill_name="document_review", rewritten_query="test", confidence=1.0
        )
        with pytest.raises(ValidationError):
            RouterDecision(
                skill_name="document_review", rewritten_query="test", confidence=1.1
            )


class TestRouterDecisionMultiMode:
    def test_multi_mode_with_plan(self):
        plan = ExecutionPlan(
            mode="sequential",
            subtasks=[
                SubTask(id="s1", skill_name="document_review", description="审阅文档A"),
                SubTask(id="s2", skill_name="knowledge-graph-extraction", description="抽取知识图谱"),
            ],
        )
        decision = RouterDecision(
            skill_name="multi_agent",
            rewritten_query="test",
            confidence=0.9,
            mode="multi",
            execution_plan=plan,
        )
        assert decision.mode == "multi"
        assert decision.execution_plan is not None
        assert len(decision.execution_plan.subtasks) == 2

    def test_parallel_mode(self):
        plan = ExecutionPlan(
            mode="parallel",
            subtasks=[
                SubTask(id="s1", skill_name="document_review", description="审阅文档"),
                SubTask(id="s2", skill_name="knowledge-graph-extraction", description="抽取图谱"),
            ],
        )
        decision = RouterDecision(
            skill_name="multi_agent",
            rewritten_query="test",
            confidence=0.85,
            mode="multi",
            execution_plan=plan,
        )
        assert decision.execution_plan.mode == "parallel"

    def test_json_roundtrip(self):
        plan = ExecutionPlan(
            mode="orchestrator",
            subtasks=[
                SubTask(id="s1", skill_name="document_review", description="审阅"),
            ],
        )
        decision = RouterDecision(
            skill_name="multi_agent",
            rewritten_query="test",
            confidence=0.9,
            mode="multi",
            execution_plan=plan,
        )
        data = decision.model_dump()
        restored = RouterDecision(**data)
        assert restored.execution_plan.mode == "orchestrator"
        assert restored.execution_plan.subtasks[0].skill_name == "document_review"
