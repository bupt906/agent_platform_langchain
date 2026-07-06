from __future__ import annotations

import pytest
from pydantic import ValidationError

from agent_platform.core.registry import SkillRegistry
from agent_platform.core.router import RouterDecision


class TestRouterDecision:
    def test_router_decision_validation(self):
        decision = RouterDecision(
            skill_name="qa",
            rewritten_query="测试问题",
            confidence=0.9,
        )
        assert decision.skill_name == "qa"
        assert decision.mode == "single"
        assert decision.execution_plan is None

    def test_router_decision_confidence_bounds(self):
        with pytest.raises(ValidationError):
            RouterDecision(
                skill_name="qa",
                rewritten_query="test",
                confidence=1.5,
            )
        with pytest.raises(ValidationError):
            RouterDecision(
                skill_name="qa",
                rewritten_query="test",
                confidence=-0.1,
            )


class TestRouterSkillDiscovery:
    def test_router_can_see_all_skills(self, skill_registry: SkillRegistry):
        names = skill_registry.skill_names()
        assert len(names) >= 3

    def test_skill_descriptions_not_empty(self, skill_registry: SkillRegistry):
        for info in skill_registry.list_skills():
            assert info.description, f"技能 {info.name} 缺少描述"

    def test_composite_skill_dependencies_visible(self, skill_registry: SkillRegistry):
        skill = skill_registry.get("data_contract_review")
        if skill:
            assert len(skill.dependencies) > 0
            assert "data_query" in skill.dependencies
            assert "contract_review" in skill.dependencies
