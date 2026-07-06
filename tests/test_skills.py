from __future__ import annotations

import pytest

from agent_platform.core.registry import SkillRegistry
from agent_platform.skills.contract_review.tools import (
    assess_risk,
    check_clause,
    parse_contract,
)
from agent_platform.skills.data_query.tools import execute_sql, get_table_schema
from agent_platform.skills.qa.tools import knowledge_search


class TestSkillRegistry:
    def test_auto_discover_finds_all_skills(self, skill_registry: SkillRegistry):
        names = skill_registry.skill_names()
        assert "qa" in names
        assert "data_query" in names
        assert "contract_review" in names

    def test_get_existing_skill(self, skill_registry: SkillRegistry):
        skill = skill_registry.get("qa")
        assert skill is not None
        assert skill.name == "qa"

    def test_get_nonexistent_skill(self, skill_registry: SkillRegistry):
        assert skill_registry.get("nonexistent") is None

    def test_list_skills_contains_info(self, skill_registry: SkillRegistry):
        skills = skill_registry.list_skills()
        assert len(skills) >= 3
        for s in skills:
            assert s.name
            assert s.description


class TestQATools:
    @pytest.mark.asyncio
    async def test_knowledge_search_returns_results(self):
        results = await knowledge_search("测试查询")
        assert len(results) > 0
        assert "content" in results[0]
        assert "source" in results[0]
        assert "score" in results[0]

    @pytest.mark.asyncio
    async def test_knowledge_search_respects_top_k(self):
        results = await knowledge_search("测试", top_k=1)
        assert len(results) == 1


class TestDataQueryTools:
    @pytest.mark.asyncio
    async def test_execute_sql_returns_rows(self):
        rows = await execute_sql("SELECT * FROM users")
        assert len(rows) > 0
        assert isinstance(rows[0], dict)

    @pytest.mark.asyncio
    async def test_get_table_schema_known_table(self):
        schema = await get_table_schema("users")
        assert "CREATE TABLE" in schema
        assert "users" in schema

    @pytest.mark.asyncio
    async def test_get_table_schema_unknown_table(self):
        schema = await get_table_schema("nonexistent")
        assert "错误" in schema


class TestContractReviewTools:
    @pytest.mark.asyncio
    async def test_parse_contract_returns_clauses(self):
        clauses = await parse_contract("测试合同文本")
        assert len(clauses) > 0

    @pytest.mark.asyncio
    async def test_check_clause_returns_result(self):
        result = await check_clause("第一条：合同标的")
        assert result.clause
        assert result.risk_level
        assert result.issue
        assert result.suggestion

    @pytest.mark.asyncio
    async def test_assess_risk_returns_assessment(self):
        result = await assess_risk(["finding1", "finding2"])
        assert "overall_risk" in result
        assert "summary" in result
        assert "recommendation" in result
