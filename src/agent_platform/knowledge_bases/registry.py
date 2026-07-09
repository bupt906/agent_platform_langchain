"""知识库注册中心。

使用 sqlite-vec 向量存储，通过 embedding 语义相似度检索知识库条文。
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

from agent_platform.knowledge_bases.vector_store import VectorStore

if TYPE_CHECKING:
    import aiosqlite

    from agent_platform.models.provider import ModelProvider

logger = logging.getLogger(__name__)

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


@dataclass
class KnowledgeBase:
    """一个审查标准知识库。"""

    name: str
    description: str
    kb_id: str
    content: str = ""
    entries: list[dict[str, str]] = field(default_factory=list)
    source_path: str = ""

    @property
    def info(self) -> dict[str, Any]:
        return {"name": self.name, "description": self.description, "id": self.kb_id, "entry_count": len(self.entries)}


@dataclass
class SearchResult:
    """知识库检索结果。"""

    kb_id: str
    kb_name: str
    entry: dict[str, str]
    relevance: float  # 0.0 ~ 1.0，余弦相似度


class KnowledgeBaseRegistry:
    """知识库注册中心。

    加载时自动将条目向量化并存入 sqlite-vec。
    检索时使用余弦相似度匹配。
    """

    def __init__(self, db_path: str = ":memory:", dimensions: int = 1536) -> None:
        self._kbs: dict[str, KnowledgeBase] = {}
        self._vector_store = VectorStore(db_path, dimensions)
        self._model_provider: ModelProvider | None = None

    @property
    def vector_store(self) -> VectorStore | None:
        return self._vector_store

    # ── 加载 ────────────────────────────────────────────────

    async def load_from_dir(
        self,
        directory: str | Path,
        model_provider: ModelProvider | None = None,
    ) -> int:
        """扫描目录中所有 .md 文件，解析条目，向量化并注册。返回加载数量。"""
        dir_path = Path(directory)
        if not dir_path.exists():
            logger.warning("知识库目录不存在: %s", dir_path)
            return 0

        self._model_provider = model_provider

        count = 0
        for md_file in dir_path.glob("*.md"):
            try:
                kb = self._parse_file(md_file)
                self._kbs[kb.kb_id] = kb
                count += 1
                logger.info("加载知识库: %s (%d 个条目)", kb.name, len(kb.entries))
            except Exception:
                logger.warning("跳过无法解析的知识库: %s", md_file, exc_info=True)

        # 向量化所有条目
        if self._vector_store and self._model_provider:
            await self._embed_all()

        return count

    def register(self, kb: KnowledgeBase) -> None:
        self._kbs[kb.kb_id] = kb

    async def reindex(self, model_provider: ModelProvider) -> None:
        """重新向量化所有已加载的知识库条目。"""
        self._model_provider = model_provider
        await self._embed_all()

    async def _embed_all(self) -> None:
        """将所有已注册 KB 的条目向量化并存入 vector_store。"""
        if not self._vector_store or not self._model_provider:
            return

        self._vector_store.clear()

        all_data: list[tuple[str, dict[str, str]]] = []
        for kb in self._kbs.values():
            for entry in kb.entries:
                all_data.append((kb.kb_id, entry))

        if not all_data:
            return

        texts_for_embed = [" ".join(e.values()) for _, e in all_data]

        logger.info("开始向量化 %d 个知识库条目...", len(texts_for_embed))
        embeddings = await self._model_provider.embed_batch(texts_for_embed)
        logger.info("向量化完成，写入存储...")

        items = [(all_data[i][0], all_data[i][1], embeddings[i]) for i in range(len(all_data))]
        self._vector_store.insert_batch(items)
        logger.info("向量存储写入完成")

    # ── 查询 ────────────────────────────────────────────────

    def get(self, kb_id: str) -> KnowledgeBase | None:
        return self._kbs.get(kb_id)

    def list_all(self) -> list[KnowledgeBase]:
        return list(self._kbs.values())

    def list_infos(self) -> list[dict[str, Any]]:
        return [kb.info for kb in self._kbs.values()]

    @property
    def count(self) -> int:
        return len(self._kbs)

    # ── 向量检索 ────────────────────────────────────────────

    async def search(
        self,
        kb_ids: list[str],
        sentence: str,
        top_k: int = 5,
        threshold: float = 0.3,
    ) -> list[SearchResult]:
        """向量语义检索——在指定知识库中查找与句子最相关的条文。

        流程：句子 → embedding → sqlite-vec 余弦相似度 → top-k 结果。

        Args:
            kb_ids: 知识库 ID 列表
            sentence: 待审查句子
            top_k: 返回数量
            threshold: 相似度阈值

        Returns:
            SearchResult 列表，按相关度降序
        """
        if not self._model_provider:
            return self._keyword_search(kb_ids, sentence)

        # 1. 生成查询向量（失败时回退到关键词检索）
        try:
            query_vec = await self._model_provider.embed(sentence)
            # 检查是否为零向量（embedding 失败的回退标记）
            if all(v == 0.0 for v in query_vec):
                return self._keyword_search(kb_ids, sentence)

            # 2. 向量检索（同步）
            raw = self._vector_store.search(query_vec, limit=top_k, threshold=threshold)
        except Exception:
            logger.warning("向量检索失败，回退到关键词检索", exc_info=True)
            return self._keyword_search(kb_ids, sentence)

        # 3. 按 kb_ids 过滤
        results: list[SearchResult] = []
        for r in raw:
            if r["kb_id"] in kb_ids:
                kb = self._kbs.get(r["kb_id"])
                results.append(
                    SearchResult(
                        kb_id=r["kb_id"],
                        kb_name=kb.name if kb else r["kb_id"],
                        entry=r["entry"],
                        relevance=r["distance"],
                    )
                )

        results.sort(key=lambda x: x.relevance, reverse=True)
        return results

    def _keyword_search(self, kb_ids: list[str], sentence: str) -> list[SearchResult]:
        """关键词匹配回退方案。"""
        results: list[SearchResult] = []
        for kb_id in kb_ids:
            kb = self._kbs.get(kb_id)
            if not kb:
                continue
            for entry in kb.entries:
                entry_text = " ".join(entry.values())
                hits = sum(1 for kw in re.findall(r"[一-鿿]{2,}|[a-zA-Z]{3,}", entry_text) if kw in sentence)
                if hits >= 1:
                    results.append(SearchResult(kb_id=kb_id, kb_name=kb.name, entry=entry, relevance=min(hits / 10.0, 1.0)))
        results.sort(key=lambda x: x.relevance, reverse=True)
        return results

    async def search_grouped(
        self,
        kb_ids: list[str],
        sentence: str,
        top_k: int = 5,
        threshold: float = 0.3,
    ) -> dict[str, list[SearchResult]]:
        """按知识库分组检索。"""
        all_results = await self.search(kb_ids, sentence, top_k, threshold)
        grouped: dict[str, list[SearchResult]] = {}
        for r in all_results:
            grouped.setdefault(r.kb_id, []).append(r)
        return grouped

    def get_kb_contents(self, kb_ids: list[str]) -> str:
        """获取指定知识库的全部内容，拼接为 prompt 上下文。"""
        parts = []
        for kb_id in kb_ids:
            kb = self._kbs.get(kb_id)
            if kb:
                parts.append(f"### {kb.name}\n{kb.content}")
        return "\n\n".join(parts)

    # ── 内部 ────────────────────────────────────────────────

    def _parse_file(self, path: Path) -> KnowledgeBase:
        text = path.read_text(encoding="utf-8")
        meta: dict[str, Any] = {}

        fm_match = _FRONTMATTER_RE.match(text)
        if fm_match:
            meta = yaml.safe_load(fm_match.group(1)) or {}
            content = text[fm_match.end():].strip()
        else:
            content = text

        entries = self._parse_entries(content)

        return KnowledgeBase(
            name=meta.get("name", path.stem),
            description=meta.get("description", ""),
            kb_id=meta.get("id", path.stem),
            content=content,
            entries=entries,
            source_path=str(path),
        )

    @staticmethod
    def _parse_entries(markdown_text: str) -> list[dict[str, str]]:
        entries = []
        current_title = ""
        current_lines: list[str] = []

        for line in markdown_text.split("\n"):
            if line.startswith("## 条目"):
                if current_title and current_lines:
                    entries.append(KnowledgeBaseRegistry._build_entry(current_title, "\n".join(current_lines)))
                current_title = line.lstrip("#").strip()
                current_lines = []
            elif current_title:
                current_lines.append(line)

        if current_title and current_lines:
            entries.append(KnowledgeBaseRegistry._build_entry(current_title, "\n".join(current_lines)))

        return entries

    @staticmethod
    def _build_entry(title: str, body: str) -> dict[str, str]:
        entry: dict[str, str] = {"标题": title, "原文": body}
        for line in body.split("\n"):
            match = re.match(r"^- (.+?)[：:]\s*(.+)", line.strip())
            if match:
                entry[match.group(1).strip()] = match.group(2).strip()
        return entry
