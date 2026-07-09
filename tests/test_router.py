from __future__ import annotations

import pytest
from pydantic import ValidationError

from agent_platform.core.registry import SkillRegistry
from agent_platform.core.router import (
    RouterDecision,
    _build_invoke_config,
    _build_router_prompt,
    resolve_route,
)


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


class TestBuildRouterPrompt:
    @pytest.mark.asyncio
    async def test_prompt_includes_all_skills(self, deps):
        prompt = _build_router_prompt(deps)
        assert "qa" in prompt
        assert "data_query" in prompt
        assert "contract_review" in prompt

    @pytest.mark.asyncio
    async def test_prompt_includes_routing_rules(self, deps):
        prompt = _build_router_prompt(deps)
        assert "single" in prompt
        assert "multi" in prompt
        assert "sequential" in prompt
        assert "parallel" in prompt
        assert "orchestrator" in prompt


class TestInvokeConfig:
    def test_no_session_id_returns_auto_thread_id(self):
        cfg = _build_invoke_config(None)
        # 持久化 checkpointer 要求必须有 thread_id，无 session_id 时自动生成
        assert "configurable" in cfg
        assert "thread_id" in cfg["configurable"]
        assert len(cfg["configurable"]["thread_id"]) > 0

    def test_with_session_id_includes_thread_id(self):
        cfg = _build_invoke_config("session-123")
        assert "configurable" in cfg
        assert cfg["configurable"]["thread_id"] == "session-123"
