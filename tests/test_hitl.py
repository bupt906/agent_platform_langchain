"""Human-in-the-Loop 模块测试。"""

from __future__ import annotations

import aiosqlite
import pytest

from agent_platform.hitl.events import ApprovalNeededEvent, ApprovalResultEvent, ReplanEvent
from agent_platform.hitl.store import ApprovalStore
from agent_platform.hitl.types import ApprovalRequest, ApprovalResponse, ApprovalStatus, ReplanRequest


@pytest.fixture
async def db():
    db = await aiosqlite.connect(":memory:")
    yield db
    await db.close()


@pytest.fixture
async def approval_store(db):
    store = ApprovalStore(db)
    await store._ensure_tables()
    return store


class TestApprovalTypes:
    """HITL 数据模型测试。"""

    def test_approval_status_enum(self):
        assert ApprovalStatus.PENDING.value == "pending"
        assert ApprovalStatus.APPROVED.value == "approved"
        assert ApprovalStatus.REJECTED.value == "rejected"
        assert ApprovalStatus.TIMEOUT.value == "timeout"

    def test_approval_request_creation(self):
        req = ApprovalRequest(
            session_id="s1",
            thread_id="t1",
            node_id="step_sql",
            skill_name="document_review",
            operation="sql_execution",
            details="执行 SQL: SELECT * FROM users",
        )
        assert req.id
        assert req.status == ApprovalStatus.PENDING
        assert req.operation == "sql_execution"

    def test_replan_request(self):
        req = ReplanRequest(
            session_id="s1",
            thread_id="t1",
            original_plan_summary="顺序执行 data_query → contract_review",
            intermediate_results={"s1": "数据查询完成"},
            proposed_revision="先审查合同再查询数据",
        )
        assert req.proposed_revision

    def test_approval_response(self):
        resp = ApprovalResponse(id="abc", status="approved", message="已批准")
        assert resp.status == "approved"


class TestApprovalStore:
    """审批存储测试。"""

    async def test_create_and_get_request(self, approval_store):
        req = ApprovalRequest(
            session_id="s1",
            thread_id="t1",
            skill_name="document_review",
            operation="sql_execution",
            details="SELECT * FROM users",
        )
        rid = await approval_store.create_request(req)
        assert rid == req.id

        fetched = await approval_store.get_request(rid)
        assert fetched is not None
        assert fetched["skill_name"] == "document_review"
        assert fetched["status"] == "pending"

    async def test_set_status(self, approval_store):
        req = ApprovalRequest(session_id="s1", thread_id="t1")
        await approval_store.create_request(req)

        await approval_store.set_status(req.id, ApprovalStatus.APPROVED, decided_by="admin")
        fetched = await approval_store.get_request(req.id)
        assert fetched["status"] == "approved"
        assert fetched["decided_by"] == "admin"

    async def test_list_pending(self, approval_store):
        await approval_store.create_request(ApprovalRequest(session_id="s1", thread_id="t1"))
        await approval_store.create_request(ApprovalRequest(session_id="s1", thread_id="t2"))

        pending = await approval_store.list_pending(session_id="s1")
        assert len(pending) == 2

    async def test_list_pending_filtered(self, approval_store):
        await approval_store.create_request(ApprovalRequest(session_id="s1", thread_id="t1"))
        await approval_store.create_request(ApprovalRequest(session_id="s2", thread_id="t2"))

        pending_s1 = await approval_store.list_pending(session_id="s1")
        assert len(pending_s1) == 1
        assert pending_s1[0]["session_id"] == "s1"

    async def test_cleanup_expired(self, approval_store):
        req = ApprovalRequest(session_id="s1", thread_id="t1")
        await approval_store.create_request(req)

        # 设置为极短的超时时间，所有请求都应该超时
        cleaned = await approval_store.cleanup_expired(timeout_seconds=0)
        assert cleaned >= 1

        fetched = await approval_store.get_request(req.id)
        assert fetched["status"] == "timeout"

    async def test_get_nonexistent_request(self, approval_store):
        result = await approval_store.get_request("nonexistent")
        assert result is None


class TestHITLEvents:
    """HITL 事件测试。"""

    def test_approval_needed_event(self):
        event = ApprovalNeededEvent(
            approval_id="abc",
            operation="sql_execution",
            skill_name="document_review",
            details="执行 SQL",
        )
        d = event.to_dict()
        assert d["type"] == "approval_needed"
        assert d["approval_id"] == "abc"

    def test_approval_result_event(self):
        event = ApprovalResultEvent(
            approval_id="abc",
            status="approved",
            message="已批准",
        )
        d = event.to_dict()
        assert d["type"] == "approval_result"
        assert d["status"] == "approved"

    def test_replan_event(self):
        event = ReplanEvent(reason="需要调整", new_plan_summary="先审查再查询")
        d = event.to_dict()
        assert d["type"] == "replan"
        assert "调整" in d["reason"]
