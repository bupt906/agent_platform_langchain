"""审计日志持久化存储。

管理 audit_log 和 tool_calls 两张表，支持查询和聚合统计。
"""

from __future__ import annotations

import logging
from typing import Any

from agent_platform.audit.schema import AuditRecord, AuditStats, ToolCallRecord

logger = logging.getLogger(__name__)

_AUDIT_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS audit_log (
    id TEXT PRIMARY KEY,
    session_id TEXT,
    timestamp TEXT NOT NULL,
    agent_type TEXT DEFAULT '',
    user_message TEXT DEFAULT '',
    assistant_message TEXT DEFAULT '',
    model_used TEXT DEFAULT '',
    tokens_prompt INTEGER DEFAULT 0,
    tokens_completion INTEGER DEFAULT 0,
    tokens_total INTEGER DEFAULT 0,
    duration_ms REAL DEFAULT 0,
    skill_used TEXT,
    router_confidence REAL,
    error TEXT
)
"""

_TOOL_CALLS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS tool_calls (
    id TEXT PRIMARY KEY,
    audit_id TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    start_time REAL DEFAULT 0,
    end_time REAL DEFAULT 0,
    duration_ms REAL DEFAULT 0,
    input_args TEXT DEFAULT '{}',
    output_summary TEXT DEFAULT '',
    success INTEGER DEFAULT 1,
    FOREIGN KEY (audit_id) REFERENCES audit_log(id)
)
"""

_INDEX_SQL = [
    "CREATE INDEX IF NOT EXISTS idx_audit_session ON audit_log(session_id);",
    "CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_log(timestamp);",
    "CREATE INDEX IF NOT EXISTS idx_audit_skill ON audit_log(skill_used);",
    "CREATE INDEX IF NOT EXISTS idx_tool_calls_audit ON tool_calls(audit_id);",
]


class AuditStore:
    """审计日志的 SQLite 持久化存储。"""

    def __init__(self, db) -> None:
        self._db = db
        self._initialized = False

    async def _ensure_tables(self) -> None:
        if self._initialized:
            return
        await self._db.execute(_AUDIT_TABLE_SQL)
        await self._db.execute(_TOOL_CALLS_TABLE_SQL)
        for idx_sql in _INDEX_SQL:
            await self._db.execute(idx_sql)
        await self._db.commit()
        self._initialized = True

    async def record(self, record: AuditRecord) -> None:
        """插入一条审计记录。"""
        await self._ensure_tables()
        await self._db.execute(
            "INSERT INTO audit_log (id, session_id, timestamp, agent_type, user_message, assistant_message, "
            "model_used, tokens_prompt, tokens_completion, tokens_total, duration_ms, skill_used, router_confidence, error) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                record.id,
                record.session_id,
                record.timestamp,
                record.agent_type,
                record.user_message,
                record.assistant_message,
                record.model_used,
                record.tokens_prompt,
                record.tokens_completion,
                record.tokens_total,
                record.duration_ms,
                record.skill_used,
                record.router_confidence,
                record.error,
            ),
        )
        await self._db.commit()

    async def record_tool_call(self, call: ToolCallRecord) -> None:
        """记录一次工具调用。"""
        await self._ensure_tables()
        await self._db.execute(
            "INSERT INTO tool_calls (id, audit_id, tool_name, start_time, end_time, duration_ms, input_args, output_summary, success) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                call.id,
                call.audit_id,
                call.tool_name,
                call.start_time,
                call.end_time,
                call.duration_ms,
                call.input_args,
                call.output_summary,
                1 if call.success else 0,
            ),
        )
        await self._db.commit()

    async def query(self, session_id: str | None = None, skill: str | None = None, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        """按条件查询审计记录。"""
        await self._ensure_tables()
        records, _ = await self.query_with_count(session_id=session_id, skill=skill, limit=limit, offset=offset)
        return records

    async def query_with_count(self, session_id: str | None = None, skill: str | None = None, limit: int = 100, offset: int = 0) -> tuple[list[dict[str, Any]], int]:
        """按条件查询审计记录，同时返回符合条件的总数。"""
        await self._ensure_tables()
        conditions = []
        params: list[Any] = []

        if session_id:
            conditions.append("session_id = ?")
            params.append(session_id)
        if skill:
            conditions.append("skill_used = ?")
            params.append(skill)

        where = "WHERE " + " AND ".join(conditions) if conditions else ""

        # 先查询总数
        count_sql = f"SELECT COUNT(*) FROM audit_log {where}"
        count_params = list(params)
        cursor = await self._db.execute(count_sql, tuple(count_params))
        count_row = await cursor.fetchone()
        total = count_row[0] if count_row else 0

        # 再查询分页数据
        data_sql = f"SELECT * FROM audit_log {where} ORDER BY timestamp DESC LIMIT ? OFFSET ?"
        data_params = list(params) + [limit, offset]
        cursor = await self._db.execute(data_sql, tuple(data_params))
        rows = await cursor.fetchall()
        return [_audit_row_to_dict(row) for row in rows], total

    async def query_tool_calls(self, audit_id: str) -> list[dict[str, Any]]:
        """查询某次 Audit 记录的工具调用链。"""
        await self._ensure_tables()
        cursor = await self._db.execute(
            "SELECT * FROM tool_calls WHERE audit_id = ? ORDER BY start_time ASC",
            (audit_id,),
        )
        rows = await cursor.fetchall()
        return [_tool_call_row_to_dict(row) for row in rows]

    async def aggregate_stats(self, days: int = 30) -> AuditStats:
        """获取最近 N 天的聚合统计。"""
        await self._ensure_tables()
        from datetime import datetime, timedelta, timezone

        since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

        cursor = await self._db.execute(
            "SELECT COUNT(*), COALESCE(SUM(tokens_total), 0), COALESCE(SUM(duration_ms), 0), "
            "COALESCE(AVG(duration_ms), 0), COALESCE(SUM(CASE WHEN error IS NOT NULL THEN 1 ELSE 0 END), 0) "
            "FROM audit_log WHERE timestamp >= ?",
            (since,),
        )
        row = await cursor.fetchone()

        # 按技能统计
        cursor2 = await self._db.execute(
            "SELECT skill_used, COUNT(*) FROM audit_log WHERE timestamp >= ? AND skill_used IS NOT NULL GROUP BY skill_used",
            (since,),
        )
        by_skill = {r[0] or "unknown": r[1] for r in await cursor2.fetchall()}

        return AuditStats(
            total_calls=row[0] or 0,
            total_tokens=row[1] or 0,
            total_duration_ms=row[2] or 0,
            avg_duration_ms=round(row[3] or 0, 1),
            by_skill=by_skill,
            errors=row[4] or 0,
        )


def _audit_row_to_dict(row: tuple) -> dict[str, Any]:
    keys = ["id", "session_id", "timestamp", "agent_type", "user_message", "assistant_message",
            "model_used", "tokens_prompt", "tokens_completion", "tokens_total", "duration_ms",
            "skill_used", "router_confidence", "error"]
    return dict(zip(keys, row))


def _tool_call_row_to_dict(row: tuple) -> dict[str, Any]:
    keys = ["id", "audit_id", "tool_name", "start_time", "end_time", "duration_ms", "input_args", "output_summary", "success"]
    return dict(zip(keys, row))
