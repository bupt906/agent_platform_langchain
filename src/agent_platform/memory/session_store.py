"""会话持久化存储。

管理 conversations 表 + FTS5 全文搜索，支持多轮对话的持久化存储和检索。
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    user_message TEXT NOT NULL,
    assistant_message TEXT NOT NULL,
    skill_used TEXT DEFAULT '',
    model_used TEXT DEFAULT '',
    tokens_used INTEGER DEFAULT 0,
    duration_ms REAL DEFAULT 0,
    created_at TEXT NOT NULL
)
"""

_FTS_SQL = """
CREATE VIRTUAL TABLE IF NOT EXISTS conversations_fts USING fts5(
    session_id, user_message, assistant_message, skill_used,
    content='conversations',
    content_rowid='id'
)
"""

_TRIGGERS_SQL = """
CREATE TRIGGER IF NOT EXISTS conversations_ai AFTER INSERT ON conversations BEGIN
    INSERT INTO conversations_fts(rowid, session_id, user_message, assistant_message, skill_used)
    VALUES (new.id, new.session_id, new.user_message, new.assistant_message, new.skill_used);
END;

CREATE TRIGGER IF NOT EXISTS conversations_ad AFTER DELETE ON conversations BEGIN
    INSERT INTO conversations_fts(conversations_fts, rowid, session_id, user_message, assistant_message, skill_used)
    VALUES ('delete', old.id, old.session_id, old.user_message, old.assistant_message, old.skill_used);
END;

CREATE TRIGGER IF NOT EXISTS conversations_au AFTER UPDATE ON conversations BEGIN
    INSERT INTO conversations_fts(conversations_fts, rowid, session_id, user_message, assistant_message, skill_used)
    VALUES ('delete', old.id, old.session_id, old.user_message, old.assistant_message, old.skill_used);
    INSERT INTO conversations_fts(rowid, session_id, user_message, assistant_message, skill_used)
    VALUES (new.id, new.session_id, new.user_message, new.assistant_message, new.skill_used);
END;
"""


class SessionStore:
    """基于 SQLite + FTS5 的会话持久化存储。"""

    _initialized: set[int] = set()

    def __init__(self, db) -> None:
        """db 是一个 aiosqlite.Connection。"""
        self._db = db

    async def ensure_tables(self) -> None:
        """幂等创建表和全文搜索索引。"""
        db_id = id(self._db)
        if db_id in SessionStore._initialized:
            return
        await self._db.executescript(_TABLE_SQL)
        await self._db.executescript(_FTS_SQL)
        await self._db.executescript(_TRIGGERS_SQL)
        await self._db.commit()
        SessionStore._initialized.add(db_id)

    async def add_turn(
        self,
        session_id: str,
        user_message: str,
        assistant_message: str,
        *,
        skill_used: str = "",
        model_used: str = "",
        tokens_used: int = 0,
        duration_ms: float = 0,
    ) -> int:
        """记录一轮对话，返回自增 id。"""
        await self.ensure_tables()
        now = datetime.now(timezone.utc).isoformat()
        cursor = await self._db.execute(
            "INSERT INTO conversations (session_id, user_message, assistant_message, skill_used, model_used, tokens_used, duration_ms, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (session_id, user_message, assistant_message, skill_used, model_used, tokens_used, duration_ms, now),
        )
        await self._db.commit()
        return cursor.lastrowid

    async def get_session_history(self, session_id: str, limit: int = 50) -> list[dict[str, Any]]:
        """获取指定会话的历史对话，按时间正序。"""
        await self.ensure_tables()
        cursor = await self._db.execute(
            "SELECT id, session_id, user_message, assistant_message, skill_used, model_used, tokens_used, duration_ms, created_at "
            "FROM conversations WHERE session_id = ? ORDER BY id ASC LIMIT ?",
            (session_id, limit),
        )
        rows = await cursor.fetchall()
        keys = ["id", "session_id", "user_message", "assistant_message", "skill_used", "model_used", "tokens_used", "duration_ms", "created_at"]
        return [dict(zip(keys, row)) for row in rows]

    async def search(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        """全文搜索历史对话。"""
        await self.ensure_tables()
        cursor = await self._db.execute(
            "SELECT c.id, c.session_id, c.user_message, c.assistant_message, c.skill_used, c.created_at "
            "FROM conversations c JOIN conversations_fts fts ON c.id = fts.rowid "
            "WHERE conversations_fts MATCH ? ORDER BY rank LIMIT ?",
            (query, limit),
        )
        rows = await cursor.fetchall()
        keys = ["id", "session_id", "user_message", "assistant_message", "skill_used", "created_at"]
        return [dict(zip(keys, row)) for row in rows]

    async def count_turns(self, session_id: str) -> int:
        """返回指定会话的对话轮次总数。"""
        await self.ensure_tables()
        cursor = await self._db.execute(
            "SELECT COUNT(*) FROM conversations WHERE session_id = ?", (session_id,)
        )
        row = await cursor.fetchone()
        return row[0] if row else 0

    async def cleanup_old(self, retention_days: int = 90) -> int:
        """清理超过 retention_days 天的记录，返回删除行数。"""
        await self.ensure_tables()
        cutoff = datetime.now(timezone.utc).timestamp() - retention_days * 86400
        cutoff_str = datetime.fromtimestamp(cutoff, tz=timezone.utc).isoformat()
        cursor = await self._db.execute(
            "DELETE FROM conversations WHERE created_at < ?", (cutoff_str,)
        )
        await self._db.commit()
        return cursor.rowcount
