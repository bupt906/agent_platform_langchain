from __future__ import annotations

import pytest

from agent_platform.core.registry import SkillRegistry
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
