"""审计日志模块测试。"""

from __future__ import annotations

import aiosqlite
import pytest

from agent_platform.audit import AuditRecord, AuditStats, AuditStore, ToolCallRecord


@pytest.fixture
async def db():
    db = await aiosqlite.connect(":memory:")
    yield db
    await db.close()


@pytest.fixture
async def audit_store(db):
    store = AuditStore(db)
    await store._ensure_tables()
    return store


class TestAuditRecord:
    """审计记录模型测试。"""

    def test_audit_record_creation(self):
        record = AuditRecord(
            session_id="s1",
            agent_type="skill:qa",
            user_message="你好",
            assistant_message="你好！",
            duration_ms=150.0,
        )
        assert record.id
        assert len(record.id) == 12
        assert record.agent_type == "skill:qa"
        assert record.error is None

    def test_audit_record_with_error(self):
        record = AuditRecord(
            agent_type="general",
            user_message="test",
            assistant_message="",
            error="连接超时",
        )
        assert record.error == "连接超时"

    def test_tool_call_record(self):
        call = ToolCallRecord(
            audit_id="abc123",
            tool_name="search_knowledge",
            duration_ms=50.0,
            input_args='{"query": "test"}',
            output_summary="找到 3 条结果",
        )
        assert call.tool_name == "search_knowledge"
        assert call.success is True


class TestAuditStore:
    """审计存储测试。"""

    async def test_record_and_query(self, audit_store):
        record = AuditRecord(
            session_id="s1",
            agent_type="skill:qa",
            user_message="测试问题",
            assistant_message="测试回答",
            skill_used="qa",
        )
        await audit_store.record(record)

        results = await audit_store.query(session_id="s1")
        assert len(results) >= 1
        assert results[0]["user_message"] == "测试问题"

    async def test_query_by_skill(self, audit_store):
        await audit_store.record(AuditRecord(session_id="s1", agent_type="skill:qa", user_message="q1", assistant_message="a1", skill_used="qa"))
        await audit_store.record(AuditRecord(session_id="s2", agent_type="skill:data_query", user_message="q2", assistant_message="a2", skill_used="data_query"))

        qa_results = await audit_store.query(skill="qa")
        assert all(r["skill_used"] == "qa" for r in qa_results)

    async def test_record_tool_call(self, audit_store):
        await audit_store.record(AuditRecord(id="rec-1", agent_type="skill:qa", user_message="q", assistant_message="a"))
        call = ToolCallRecord(audit_id="rec-1", tool_name="search", duration_ms=10.0)
        await audit_store.record_tool_call(call)

        calls = await audit_store.query_tool_calls("rec-1")
        assert len(calls) == 1
        assert calls[0]["tool_name"] == "search"

    async def test_aggregate_stats(self, audit_store):
        await audit_store.record(AuditRecord(agent_type="skill:qa", user_message="q1", assistant_message="a1", skill_used="qa", duration_ms=100, tokens_total=50))
        await audit_store.record(AuditRecord(agent_type="skill:data_query", user_message="q2", assistant_message="a2", skill_used="data_query", duration_ms=200, tokens_total=100))

        stats = await audit_store.aggregate_stats(days=30)
        assert isinstance(stats, AuditStats)
        assert stats.total_calls >= 2
        assert stats.total_tokens >= 150
        assert stats.total_duration_ms >= 300

    async def test_query_pagination(self, audit_store):
        for i in range(5):
            await audit_store.record(AuditRecord(agent_type="general", user_message=f"q{i}", assistant_message=f"a{i}"))

        results = await audit_store.query(limit=2, offset=0)
        assert len(results) <= 2
