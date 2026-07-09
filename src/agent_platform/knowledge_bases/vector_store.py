"""向量存储 — 优先使用 sqlite-vec，不可用时降级为纯 Python 余弦相似度。"""

from __future__ import annotations

import json
import logging
import math
import sqlite3
import struct
from typing import Any

logger = logging.getLogger(__name__)


class VectorStore:
    """向量存储，支持余弦相似度检索。

    优先使用 sqlite-vec 扩展做向量检索；如果扩展无法加载（如 macOS 自带 sqlite3），
    自动降级为全量 Python 余弦相似度计算。
    """

    def __init__(self, db_path: str = ":memory:", dimensions: int = 1536) -> None:
        self._db_path = db_path
        self._dimensions = dimensions
        self._conn: sqlite3.Connection | None = None
        self._initialized = False
        self._use_vec_extension = False

    def _ensure_tables(self) -> None:
        if self._initialized:
            return

        self._conn = sqlite3.connect(self._db_path)
        self._conn.row_factory = sqlite3.Row

        # 尝试加载 sqlite-vec 扩展
        if self._try_load_extension():
            self._conn.execute(f"""
                CREATE VIRTUAL TABLE IF NOT EXISTS vec_entries USING vec0(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    embedding FLOAT[{self._dimensions}]
                )
            """)
            self._use_vec_extension = True
            logger.info("sqlite-vec 扩展加载成功，使用向量索引检索")
        else:
            # 降级：用普通表存 BLOB
            self._conn.execute(f"""
                CREATE TABLE IF NOT EXISTS vec_entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    embedding BLOB NOT NULL
                )
            """)
            logger.warning("sqlite-vec 扩展不可用，降级为 Python 余弦相似度检索")

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

    def _try_load_extension(self) -> bool:
        """尝试加载 sqlite-vec 扩展，失败返回 False。"""
        try:
            self._conn.enable_load_extension(True)
        except AttributeError:
            return False
        try:
            import sqlite_vec
            self._conn.load_extension(sqlite_vec.loadable_path())
            return True
        except Exception:
            return False

    # ── CRUD ────────────────────────────────────────────────

    def insert(self, kb_id: str, entry: dict[str, str], embedding: list[float]) -> int:
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
        self._ensure_tables()

        if self._use_vec_extension:
            return self._search_vec_extension(query_vec, limit, threshold)
        else:
            return self._search_python(query_vec, limit, threshold)

    def _search_vec_extension(
        self, query_vec: list[float], limit: int, threshold: float
    ) -> list[dict[str, Any]]:
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
        return self._build_results(cur.fetchall(), threshold)

    def _search_python(
        self, query_vec: list[float], limit: int, threshold: float
    ) -> list[dict[str, Any]]:
        """降级方案：Python 逐行计算余弦相似度。"""
        cur = self._conn.execute("""
            SELECT v.id, v.embedding, m.kb_id, m.entry_json, m.entry_text
            FROM vec_entries v
            JOIN vec_metadata m ON v.id = m.rowid
        """)
        rows = cur.fetchall()

        scored = []
        for row in rows:
            emb = _deserialize_vec(row["embedding"])
            distance = _cosine_distance(query_vec, emb)
            scored.append((row, distance))

        scored.sort(key=lambda x: x[1])
        scored = scored[:min(limit, 100)]

        results = []
        for row, distance in scored:
            if distance > threshold:
                continue
            results.append({
                "rowid": row["id"],
                "distance": round(distance, 4),
                "kb_id": row["kb_id"],
                "entry": json.loads(row["entry_json"]),
                "entry_text": row["entry_text"],
            })
        return results

    def _build_results(self, rows: list[Any], threshold: float) -> list[dict[str, Any]]:
        results = []
        for row in rows:
            distance = row["distance"] if isinstance(row, dict) else row[1]
            if distance > threshold:
                continue
            results.append({
                "rowid": row["id"] if isinstance(row, dict) else row[0],
                "distance": round(distance, 4),
                "kb_id": row["kb_id"] if isinstance(row, dict) else row[2],
                "entry": json.loads(row["entry_json"] if isinstance(row, dict) else row[3]),
                "entry_text": row["entry_text"] if isinstance(row, dict) else row[4],
            })
        return results

    def clear(self) -> None:
        self._ensure_tables()
        self._conn.execute("DELETE FROM vec_metadata")
        self._conn.execute("DELETE FROM vec_entries")
        self._conn.commit()

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None


# ── 工具函数 ────────────────────────────────────────────────


def _serialize_vec(vec: list[float]) -> bytes:
    return struct.pack(f"<{len(vec)}f", *vec)


def _deserialize_vec(blob: bytes) -> list[float]:
    n = len(blob) // 4
    return list(struct.unpack(f"<{n}f", blob))


def _cosine_distance(a: list[float], b: list[float]) -> float:
    """计算余弦距离，范围 [0, 2]。0 = 方向完全一致，2 = 方向完全相反。"""
    if len(a) != len(b):
        return 2.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 2.0
    cosine_sim = dot / (norm_a * norm_b)
    cosine_sim = max(-1.0, min(1.0, cosine_sim))
    return 1.0 - cosine_sim
