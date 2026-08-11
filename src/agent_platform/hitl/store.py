"""审批请求的持久化存储。"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from agent_platform.hitl.types import ApprovalRequest, ApprovalStatus

logger = logging.getLogger(__name__)

_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS approval_requests (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    thread_id TEXT NOT NULL,
    node_id TEXT DEFAULT '',
    skill_name TEXT DEFAULT '',
    operation TEXT DEFAULT '',
    details TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    status TEXT DEFAULT 'pending',
    decided_by TEXT,
    decided_at TEXT
)
"""

_INDEX_SQL = [
    "CREATE INDEX IF NOT EXISTS idx_approval_session ON approval_requests(session_id);",
    "CREATE INDEX IF NOT EXISTS idx_approval_status ON approval_requests(status);",
    "CREATE INDEX IF NOT EXISTS idx_approval_thread ON approval_requests(thread_id);",
]


class ApprovalStore:
    """审批请求的 SQLite 持久化存储。"""

    def __init__(self, db) -> None:
        self._db = db
        self._initialized = False

    async def _ensure_tables(self) -> None:
        if self._initialized:
            return
        await self._db.execute(_TABLE_SQL)
        for idx_sql in _INDEX_SQL:
            await self._db.execute(idx_sql)
        await self._db.commit()
        self._initialized = True

    async def create_request(self, req: ApprovalRequest) -> str:
        """创建一条审批请求，返回 id。"""
        await self._ensure_tables()
        await self._db.execute(
            "INSERT INTO approval_requests (id, session_id, thread_id, node_id, skill_name, operation, details, created_at, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (req.id, req.session_id, req.thread_id, req.node_id, req.skill_name, req.operation, req.details, req.created_at, req.status.value),
        )
        await self._db.commit()
        return req.id

    async def get_request(self, approval_id: str) -> dict[str, Any] | None:
        """获取指定审批请求。"""
        await self._ensure_tables()
        cursor = await self._db.execute(
            "SELECT * FROM approval_requests WHERE id = ?", (approval_id,)
        )
        row = await cursor.fetchone()
        if not row:
            return None
        keys = ["id", "session_id", "thread_id", "node_id", "skill_name", "operation", "details", "created_at", "status", "decided_by", "decided_at"]
        return dict(zip(keys, row, strict=True))

    async def set_status(self, approval_id: str, status: ApprovalStatus, decided_by: str = "") -> None:
        """更新审批状态。"""
        await self._ensure_tables()
        now = datetime.now(timezone.utc).isoformat()
        await self._db.execute(
            "UPDATE approval_requests SET status = ?, decided_by = ?, decided_at = ? WHERE id = ?",
            (status.value, decided_by, now, approval_id),
        )
        await self._db.commit()

    async def list_pending(self, session_id: str | None = None, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        """列出待审批的请求。"""
        await self._ensure_tables()
        keys = ["id", "session_id", "thread_id", "node_id", "skill_name", "operation", "details", "created_at", "status", "decided_by", "decided_at"]
        if session_id:
            cursor = await self._db.execute(
                "SELECT * FROM approval_requests WHERE status = 'pending' AND session_id = ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (session_id, limit, offset),
            )
        else:
            cursor = await self._db.execute(
                "SELECT * FROM approval_requests WHERE status = 'pending' ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (limit, offset),
            )
        rows = await cursor.fetchall()
        return [dict(zip(keys, row, strict=True)) for row in rows]

    async def cleanup_expired(self, timeout_seconds: int = 300) -> int:
        """将超时的审批请求标记为 timeout，返回更新行数。"""
        await self._ensure_tables()
        cutoff = datetime.now(timezone.utc).timestamp() - timeout_seconds
        cutoff_str = datetime.fromtimestamp(cutoff, tz=timezone.utc).isoformat()
        cursor = await self._db.execute(
            "UPDATE approval_requests SET status = ? WHERE status = 'pending' AND created_at < ?",
            (ApprovalStatus.TIMEOUT.value, cutoff_str),
        )
        await self._db.commit()
        return cursor.rowcount
