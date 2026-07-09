"""基于 sqlite-vec 的向量存储。

轻量级本地向量数据库，零外部依赖，嵌入到 SQLite 中运行。
使用原生 sqlite3（同步）以支持 extension 加载。
"""

from __future__ import annotations

import json
import logging
import sqlite3
import struct
from typing import Any

logger = logging.getLogger(__name__)


class VectorStore:
    """sqlite-vec 向量存储，支持余弦相似度检索。"""

    def __init__(self, db_path: str = ":memory:", dimensions: int = 1536) -> None:
        self._db_path = db_path
        self._dimensions = dimensions
        self._conn: sqlite3.Connection | None = None
        self._initialized = False

    def _ensure_tables(self) -> None:
        if self._initialized:
            return
        if not self._conn:
            self._conn = sqlite3.connect(self._db_path)
            self._conn.enable_load_extension(True)
            import sqlite_vec

            self._conn.load_extension(sqlite_vec.loadable_path())

        self._conn.execute(f"""
            CREATE VIRTUAL TABLE IF NOT EXISTS vec_entries USING vec0(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                embedding FLOAT[{self._dimensions}]
            )
        """)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS vec_metadata (
                rowid INTEGER PRIMARY KEY,
                kb_id TEXT NOT NULL,
                entry_json TEXT NOT NULL,
                entry_text TEXT NOT NULL,
                FOREIGN KEY (rowid) REFERENCES vec_entries(id)
            )
        """)
        self._conn.commit()
        self._initialized = True

    def insert(self, kb_id: str, entry: dict[str, str], embedding: list[float]) -> int:
        """插入一条向量 + 元数据，返回 rowid。"""
        self._ensure_tables()

        blob = _serialize_vec(embedding)
        entry_json = json.dumps(entry, ensure_ascii=False)
        entry_text = " ".join(entry.values())

        cur = self._conn.execute("INSERT INTO vec_entries (embedding) VALUES (?)", (blob,))
        rowid = cur.lastrowid
        self._conn.execute(
            "INSERT INTO vec_metadata (rowid, kb_id, entry_json, entry_text) VALUES (?, ?, ?, ?)",
            (rowid, kb_id, entry_json, entry_text),
        )
        self._conn.commit()
        return rowid

    def insert_batch(self, items: list[tuple[str, dict[str, str], list[float]]]) -> list[int]:
        """批量插入。每个 item 为 (kb_id, entry, embedding)。"""
        self._ensure_tables()
        ids = []
        for kb_id, entry, emb in items:
            rid = self.insert(kb_id, entry, emb)
            ids.append(rid)
        return ids

    def search(
        self,
        query_vec: list[float],
        limit: int = 5,
        threshold: float = 0.3,
    ) -> list[dict[str, Any]]:
        """余弦相似度检索，返回 top-k 结果。"""
        self._ensure_tables()

        blob = _serialize_vec(query_vec)
        cur = self._conn.execute(
            """
            SELECT v.id, v.distance, m.kb_id, m.entry_json, m.entry_text
            FROM vec_entries v
            JOIN vec_metadata m ON v.id = m.rowid
            WHERE v.embedding MATCH ? AND k = ?
            ORDER BY v.distance ASC
            """,
            (blob, min(limit, 100)),
        )
        rows = cur.fetchall()

        results = []
        for row in rows:
            distance = row[1]
            # 余弦距离：0=完全匹配，2=完全相反。只保留 distance <= threshold 的结果
            if distance > threshold:
                continue
            results.append({
                "rowid": row[0],
                "distance": round(distance, 4),
                "kb_id": row[2],
                "entry": json.loads(row[3]),
                "entry_text": row[4],
            })
        return results

    def clear(self) -> None:
        """清空所有向量数据。"""
        self._ensure_tables()
        self._conn.execute("DELETE FROM vec_metadata")
        self._conn.execute("DELETE FROM vec_entries")
        self._conn.commit()

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None


def _serialize_vec(vec: list[float]) -> bytes:
    return struct.pack(f"<{len(vec)}f", *vec)
