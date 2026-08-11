from __future__ import annotations

from types import SimpleNamespace

import pytest

from agent_platform.api.routes.skills import list_skills
from agent_platform.core.registry import SkillRegistry
from agent_platform.skills.registry import DeclarativeSkillRegistry


class TestSkillRegistry:
    def test_auto_discover_finds_document_review(self, skill_registry: SkillRegistry):
        names = skill_registry.skill_names()
        assert "document_review" in names

    def test_get_existing_skill(self, skill_registry: SkillRegistry):
        skill = skill_registry.get("document_review")
        assert skill is not None
        assert skill.name == "document_review"

    def test_get_nonexistent_skill(self, skill_registry: SkillRegistry):
        assert skill_registry.get("nonexistent") is None

    def test_list_skills_contains_info(self, skill_registry: SkillRegistry):
        skills = skill_registry.list_skills()
        assert len(skills) >= 1
        for s in skills:
            assert s.name
            assert s.description

    def test_get_all_skills_returns_dict(self, skill_registry: SkillRegistry):
        all_skills = skill_registry.get_all_skills()
        assert isinstance(all_skills, dict)
        assert len(all_skills) >= 1
        assert "document_review" in all_skills

    def test_create_agent_with_checkpointer(self, skill_registry: SkillRegistry, model_provider):
        from langgraph.checkpoint.memory import InMemorySaver

        skill = skill_registry.get("document_review")
        agent = skill.create_agent(model_provider, checkpointer=InMemorySaver())
        assert agent is not None

    def test_create_agent_without_checkpointer(self, skill_registry: SkillRegistry, model_provider):
        skill = skill_registry.get("document_review")
        agent = skill.create_agent(model_provider, checkpointer=None)
        assert agent is not None


@pytest.mark.asyncio
async def test_skills_endpoint_lists_agents_and_declarative_skills(deps) -> None:
    from agent_platform.tools import register_all_declarative_tools

    register_all_declarative_tools()
    deps.declarative_registry = DeclarativeSkillRegistry()
    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(deps=deps)),
    )

    response = await list_skills(request)
    items = {item.name: item for item in response.skills}

    assert items["document_review"].kind == "agent"
    assert items["knowledge-graph-extraction"].kind == "skill"
    assert items["knowledge-graph-extraction"].tools == [
        "read_file",
        "write_file",
        "edit_file",
        "bash",
    ]
    assert items["knowledge-graph-extraction"].ready is True
    assert items["knowledge-graph-extraction"].missing_tools == []


@pytest.mark.asyncio
async def test_skills_endpoint_exposes_quarantined_skills(tmp_path, deps) -> None:
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

    deps.declarative_registry = DeclarativeSkillRegistry(tmp_path, validator=reject_missing_tool)
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(deps=deps)))

    response = await list_skills(request)
    item = next(item for item in response.skills if item.name == "broken")

    assert item.kind == "skill"
    assert item.ready is False
    assert item.unavailable_reason == "工具未注册: missing_tool"
