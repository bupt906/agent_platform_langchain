"""Prompt 缓存模块测试。"""

from __future__ import annotations

import pytest

from agent_platform.prompts.builder import LayeredPromptBuilder
from agent_platform.prompts.templates import (
    AGENT_IDENTITY_STABLE,
    GENERAL_AGENT_STABLE,
    ROUTER_RULES_STABLE,
    SYNTHESIS_DEFAULT,
)
from agent_platform.skills.registry import DeclarativeSkillRegistry


class TestPromptTemplates:
    """模板常量测试。"""

    def test_router_rules_not_empty(self):
        assert len(ROUTER_RULES_STABLE) > 50
        assert "智能路由器" in ROUTER_RULES_STABLE
        assert "mode" in ROUTER_RULES_STABLE

    def test_agent_identity_not_empty(self):
        assert len(AGENT_IDENTITY_STABLE) > 20
        assert "智能助手" in AGENT_IDENTITY_STABLE

    def test_general_agent_not_empty(self):
        assert len(GENERAL_AGENT_STABLE) > 5

    def test_synthesis_default(self):
        assert "综合" in SYNTHESIS_DEFAULT or len(SYNTHESIS_DEFAULT) > 10


class TestLayeredPromptBuilder:
    """分层 Prompt 构建器测试。"""

    @pytest.fixture
    def builder(self):
        return LayeredPromptBuilder(cache_ttl=300)

    def test_get_stable_layer_known_skill(self, builder):
        prompt = builder.get_stable_layer("document_review")
        assert "文档审阅" in prompt
        assert len(prompt) > 20

    def test_get_stable_layer_unknown_skill(self, builder):
        prompt = builder.get_stable_layer("unknown_skill")
        assert len(prompt) > 5  # 回退到通用 prompt

    def test_get_stable_layer_cached(self, builder):
        p1 = builder.get_stable_layer("document_review")
        p2 = builder.get_stable_layer("document_review")
        assert p1 == p2  # LRU 缓存保证相同

    def test_get_router_stable(self, builder):
        prompt = builder.get_router_stable()
        assert "智能路由器" in prompt
        assert "路由规则" in prompt

    def test_build_volatile(self, builder):
        result = builder.build_volatile(
            "用户问题",
            history=[
                {"role": "user", "content": "之前的问题"},
                {"role": "assistant", "content": "之前的回答"},
            ],
        )
        assert "用户问题" in result
        assert "之前的问题" in result

    def test_build_volatile_no_history(self, builder):
        result = builder.build_volatile("查询")
        assert "用户问题" in result
        assert "查询" in result

    def test_build_skill_prompt(self, builder):
        prompt = builder.build_skill_prompt("document_review", "查询")
        assert len(prompt) > 10

    def test_context_layer_caching(self, builder, skill_registry):
        """上下文层应该被缓存。"""
        c1 = builder.get_context_layer(skill_registry)
        c2 = builder.get_context_layer(skill_registry)
        assert c1 == c2
        assert "document_review" in c1
        assert "document_review" in c1

    def test_build_router_prompt(self, builder, skill_registry):
        prompt = builder.build_router_prompt(skill_registry)
        assert "智能路由器" in prompt
        assert "可用技能" in prompt
        assert "document_review" in prompt

    def test_build_router_prompt_includes_declarative_skills(
        self,
        builder,
        skill_registry,
    ):
        prompt = builder.build_router_prompt(
            skill_registry,
            DeclarativeSkillRegistry(),
        )

        assert "knowledge-graph-extraction" in prompt
        assert "声明式 Skill" in prompt
        assert "read_file" in prompt
