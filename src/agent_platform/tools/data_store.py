"""数据存储 — 按 session_id + data_key 存取结构化数据。

目前使用内存字典存储。生产环境可替换为 parquet 文件或 Redis。
"""

from __future__ import annotations

import logging
import time

logger = logging.getLogger(__name__)

_store: dict[str, dict[str, list[dict]]] = {}
_session_timestamps: dict[str, float] = {}  # 记录 session 最后活跃时间

_MAX_SESSIONS = 500  # 最大 session 数，超出后清理最旧的


def _touch_session(session_id: str) -> None:
    """记录 session 活跃时间，超限时清理最旧 session。"""
    _session_timestamps[session_id] = time.monotonic()
    if len(_session_timestamps) > _MAX_SESSIONS:
        # 按活跃时间排序，删除最旧的
        sorted_sessions = sorted(_session_timestamps.items(), key=lambda x: x[1])
        to_remove = len(_session_timestamps) - _MAX_SESSIONS
        for sid, _ in sorted_sessions[:to_remove]:
            _store.pop(sid, None)
            _session_timestamps.pop(sid, None)


def save_dataframe(session_id: str, data_key: str, rows: list[dict]) -> str:
    """保存数据行（list-of-dict 格式），返回 data_key。"""
    _store.setdefault(session_id, {})[data_key] = rows
    _touch_session(session_id)
    logger.info("data_store: saved %s/%s (%d rows)", session_id, data_key, len(rows))
    return data_key


def load_dataframe(session_id: str, data_key: str) -> list[dict]:
    """按 session_id + data_key 加载数据行。"""
    if session_id not in _store or data_key not in _store[session_id]:
        raise KeyError(f"data_key '{data_key}' not found for session {session_id}")
    _touch_session(session_id)
    return _store[session_id][data_key]


def list_keys(session_id: str) -> list[str]:
    return list(_store.get(session_id, {}).keys())


def get_manifest(session_id: str) -> dict[str, dict]:
    """获取所有 data_key 的概要信息。"""
    manifest = {}
    for key, rows in _store.get(session_id, {}).items():
        cols = list(rows[0].keys()) if rows else []
        manifest[key] = {
            "row_count": len(rows),
            "columns": cols,
        }
    return manifest


def clear_session(session_id: str) -> None:
    _store.pop(session_id, None)
    _session_timestamps.pop(session_id, None)
