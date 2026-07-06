from __future__ import annotations

import pytest
from pydantic import ValidationError

from agent_platform.core.registry import SkillRegistry
from agent_platform.core.router import RouterDecision
from agent_platform.graph.patterns import ExecutionPlan, SubTask


class TestRouterDecisionBackwardCompat:
    def test_single_mode_defaults(self):
        decision = RouterDecision(
            skill_name="qa",
            rewritten_query="test",
            confidence=0.8,
        )
        assert decision.mode == "single"
        assert decision.execution_plan is None

    def test_confidence_bounds(self):
        RouterDecision(
            skill_name="qa", rewritten_query="test", confidence=0.0
        )
        RouterDecision(
            skill_name="qa", rewritten_query="test", confidence=1.0
        )
        with pytest.raises(ValidationError):
            RouterDecision(
                skill_name="qa", rewritten_query="test", confidence=1.1
            )


class TestRouterDecisionMultiMode:
    def test_multi_mode_with_plan(self):
        plan = ExecutionPlan(
            mode="sequential",
            subtasks=[
                SubTask(id="s1", skill_name="data_query", description="查询数据"),
                SubTask(id="s2", skill_name="contract_review", description="审查合同"),
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
                SubTask(id="s1", skill_name="qa", description="检索"),
                SubTask(id="s2", skill_name="data_query", description="查询"),
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
                SubTask(id="s1", skill_name="qa", description="检索"),
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
        assert restored.execution_plan.subtasks[0].skill_name == "qa"


class TestCompositeSkillDiscovery:
    def test_composite_skill_discovered(self, skill_registry: SkillRegistry):
        skill = skill_registry.get("data_contract_review")
        assert skill is not None

    def test_dependency_visibility(self, skill_registry: SkillRegistry):
        skill = skill_registry.get("data_contract_review")
        if skill:
            info = skill.info
            assert "data_query" in info.dependencies
            assert "contract_review" in info.dependencies

    def test_dependencies_in_skill_info(self, skill_registry: SkillRegistry):
        for info in skill_registry.list_skills():
            if info.name == "data_contract_review":
                assert len(info.dependencies) == 2
                break
