from __future__ import annotations

import pytest
from pydantic import ValidationError

import agent_platform.core.router as router_module
from agent_platform.core.registry import SkillRegistry
from agent_platform.core.router import (
    RouterDecision,
    _build_invoke_config,
    _build_router_prompt,
    execute_decision,
)
from agent_platform.skills.registry import DeclarativeSkillRegistry


class TestRouterDecision:
    def test_router_decision_validation(self):
        decision = RouterDecision(
            skill_name="document_review",
            rewritten_query="测试问题",
            confidence=0.9,
        )
        assert decision.skill_name == "document_review"
        assert decision.mode == "single"
        assert decision.execution_plan is None

    def test_router_decision_confidence_bounds(self):
        with pytest.raises(ValidationError):
            RouterDecision(
                skill_name="document_review",
                rewritten_query="test",
                confidence=1.5,
            )
        with pytest.raises(ValidationError):
            RouterDecision(
                skill_name="document_review",
                rewritten_query="test",
                confidence=-0.1,
            )


class TestRouterSkillDiscovery:
    def test_router_can_see_all_skills(self, skill_registry: SkillRegistry):
        names = skill_registry.skill_names()
        assert len(names) >= 1

    def test_skill_descriptions_not_empty(self, skill_registry: SkillRegistry):
        for info in skill_registry.list_skills():
            assert info.description, f"技能 {info.name} 缺少描述"


class TestBuildRouterPrompt:
    @pytest.mark.asyncio
    async def test_prompt_includes_all_skills(self, deps):
        prompt = _build_router_prompt(deps)
        assert "document_review" in prompt

    @pytest.mark.asyncio
    async def test_prompt_includes_declarative_skills_and_tools(self, deps):
        deps.declarative_registry = DeclarativeSkillRegistry()

        prompt = _build_router_prompt(deps)

        assert "knowledge-graph-extraction" in prompt
        assert "声明式 Skill" in prompt
        assert "read_file" in prompt
        assert "bash" in prompt

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


def _build_unavailable_registry(tmp_path):
    skill_dir = tmp_path / "broken"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        """---
name: broken
description: Broken skill
tools: [missing_tool]
---

# Broken
""",
        encoding="utf-8",
    )

    def reject_missing_tool(_skill):
        raise RuntimeError("工具未注册: missing_tool")

    return DeclarativeSkillRegistry(tmp_path, validator=reject_missing_tool)


@pytest.mark.asyncio
async def test_unavailable_skill_falls_back_to_general(tmp_path, deps, monkeypatch):
    deps.declarative_registry = _build_unavailable_registry(tmp_path)
    decision = RouterDecision(skill_name="broken", rewritten_query="测试问题", confidence=1.0)

    async def fake_general(message, _deps, _model_id, _invoke_cfg):
        return f"general:{message}", {"prompt": 1, "completion": 1, "total": 2}

    monkeypatch.setattr(router_module, "_general_response", fake_general)

    reply = await execute_decision(decision, "测试问题", deps)

    assert reply == "general:测试问题"
    assert decision.skill_name == "general"
    assert decision.requested_skill_name == "broken"
    assert decision.fallback_reason == "declarative_skill_unavailable: 工具未注册: missing_tool"


@pytest.mark.asyncio
async def test_unknown_skill_falls_back_to_general(deps, monkeypatch):
    deps.declarative_registry = DeclarativeSkillRegistry()
    decision = RouterDecision(skill_name="missing-skill", rewritten_query="测试问题", confidence=0.9)

    class CapturingAuditStore:
        record_value = None

        async def record(self, record):
            self.record_value = record

    audit_store = CapturingAuditStore()
    deps.audit_store = audit_store

    async def fake_general(message, _deps, _model_id, _invoke_cfg):
        return f"general:{message}", {"prompt": 1, "completion": 1, "total": 2}

    monkeypatch.setattr(router_module, "_general_response", fake_general)

    reply = await execute_decision(decision, "测试问题", deps)

    assert reply == "general:测试问题"
    assert decision.skill_name == "general"
    assert decision.requested_skill_name == "missing-skill"
    assert decision.fallback_reason == "skill_not_found"
    assert audit_store.record_value.requested_skill == "missing-skill"
    assert audit_store.record_value.fallback_reason == "skill_not_found"


@pytest.mark.asyncio
async def test_runtime_skill_configuration_error_falls_back_to_general(deps, monkeypatch):
    deps.declarative_registry = DeclarativeSkillRegistry()

    async def fail_skill(*_args, **_kwargs):
        raise RuntimeError("工具未注册: missing_tool")

    async def fake_general(message, _deps, _model_id, _invoke_cfg):
        return f"general:{message}", {"prompt": 1, "completion": 1, "total": 2}

    monkeypatch.setattr(router_module, "_execute_declarative_skill", fail_skill)
    monkeypatch.setattr(router_module, "_general_response", fake_general)

    decision = RouterDecision(
        skill_name="knowledge-graph-extraction",
        rewritten_query="测试问题",
        confidence=1.0,
    )
    reply = await execute_decision(decision, "测试问题", deps)

    assert reply == "general:测试问题"
    assert decision.skill_name == "general"
    assert decision.requested_skill_name == "knowledge-graph-extraction"
    assert decision.fallback_reason == "declarative_skill_execution_error: 工具未注册: missing_tool"
