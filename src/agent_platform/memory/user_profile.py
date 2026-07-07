"""用户画像持久化。

存储和检索用户偏好、上下文信息，使 Agent 在不同 session 间保持对用户的认知。
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS user_profiles (
    session_id TEXT PRIMARY KEY,
    profile_json TEXT DEFAULT '{}',
    preferences_json TEXT DEFAULT '{}',
    updated_at TEXT NOT NULL
)
"""


class UserProfileStore:
    """管理用户画像和偏好的持久化存储。"""

    def __init__(self, db) -> None:
        """db 是一个 aiosqlite.Connection。"""
        self._db = db
        self._initialized = False

    async def _ensure_tables(self) -> None:
        if self._initialized:
            return
        await self._db.execute(_TABLE_SQL)
        await self._db.commit()
        self._initialized = True

    async def get_profile(self, session_id: str) -> dict[str, Any]:
        """获取用户画像，返回 {"profile": {...}, "preferences": {...}}。"""
        await self._ensure_tables()
        cursor = await self._db.execute(
            "SELECT profile_json, preferences_json, updated_at FROM user_profiles WHERE session_id = ?",
            (session_id,),
        )
        row = await cursor.fetchone()
        if not row:
            return {"profile": {}, "preferences": {}, "updated_at": None}
        return {
            "profile": json.loads(row[0]),
            "preferences": json.loads(row[1]),
            "updated_at": row[2],
        }

    async def update_profile(self, session_id: str, profile: dict[str, Any]) -> None:
        """创建或更新用户画像。"""
        await self._ensure_tables()
        now = datetime.now(timezone.utc).isoformat()
        profile_json = json.dumps(profile, ensure_ascii=False)
        await self._db.execute(
            "INSERT OR REPLACE INTO user_profiles (session_id, profile_json, updated_at) VALUES (?, ?, ?)",
            (session_id, profile_json, now),
        )
        await self._db.commit()

    async def merge_preferences(self, session_id: str, prefs: dict[str, Any]) -> None:
        """合并偏好设置（增量更新，不覆盖已有的其他偏好键）。"""
        await self._ensure_tables()
        existing = await self.get_profile(session_id)
        merged = {**existing["preferences"], **prefs}
        now = datetime.now(timezone.utc).isoformat()
        await self._db.execute(
            "INSERT INTO user_profiles (session_id, profile_json, preferences_json, updated_at) "
            "VALUES (?, ?, ?, ?) ON CONFLICT(session_id) DO UPDATE SET "
            "preferences_json = excluded.preferences_json, updated_at = excluded.updated_at",
            (session_id, json.dumps(existing["profile"], ensure_ascii=False), json.dumps(merged, ensure_ascii=False), now),
        )
        await self._db.commit()

    async def get_preference(self, session_id: str, key: str, default: Any = None) -> Any:
        """获取单个偏好值。"""
        data = await self.get_profile(session_id)
        return data["preferences"].get(key, default)
