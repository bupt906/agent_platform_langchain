"""技能手册系统 —— 特定场景的"操作说明书"。

与 agents/ 不同：agents 是自主决策的 AI，skill manuals 是告知 LLM "怎么做的操作指南"。

手册格式: Markdown + YAML frontmatter

    ---
    name: ppt
    description: PowerPoint 操作指南
    keywords: [PPT, PowerPoint, 幻灯片, 演示文稿]
    ---
    # PPT 操作指南
    ...

每次请求时，路由器检查是否匹配某个手册领域，如命中则将手册全文注入 system prompt。
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


@dataclass
class SkillManual:
    name: str
    description: str
    keywords: list[str] = field(default_factory=list)
    content: str = ""  # frontmatter 之后的正文（纯 markdown）
    source_path: str = ""

    @property
    def info(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "keywords": self.keywords,
        }


class SkillManualRegistry:
    """技能手册注册中心，负责从目录加载 / 解析 / 匹配手册。"""

    def __init__(self, manuals_dir: str | Path | None = None) -> None:
        self._manuals: dict[str, SkillManual] = {}
        self._dir: Path | None = Path(manuals_dir) if manuals_dir else None

    # ── 加载 ────────────────────────────────────────────────

    def load_from_dir(self, directory: str | Path) -> int:
        """扫描目录中所有 .md 文件，解析并注册。返回加载数。"""
        self._dir = Path(directory)
        count = 0

        if not self._dir.exists():
            logger.warning("技能手册目录不存在: %s", self._dir)
            return 0

        for md_file in self._dir.glob("*.md"):
            try:
                manual = self._parse_file(md_file)
                self._manuals[manual.name] = manual
                count += 1
                logger.info("加载技能手册: %s (%d 个关键词)", manual.name, len(manual.keywords))
            except Exception:
                logger.warning("跳过无法解析的手册: %s", md_file, exc_info=True)

        return count

    def register(self, manual: SkillManual) -> None:
        self._manuals[manual.name] = manual

    def unregister(self, name: str) -> bool:
        if name in self._manuals:
            del self._manuals[name]
            return True
        return False

    # ── 查询 ────────────────────────────────────────────────

    def get(self, name: str) -> SkillManual | None:
        return self._manuals.get(name)

    def list_all(self) -> list[SkillManual]:
        return list(self._manuals.values())

    def list_infos(self) -> list[dict[str, Any]]:
        return [m.info for m in self._manuals.values()]

    @property
    def count(self) -> int:
        return len(self._manuals)

    # ── 匹配 ────────────────────────────────────────────────

    def match(self, query: str) -> SkillManual | None:
        """基于关键词匹配最相关的手册。

        策略：query 中出现的 keyword 越多，匹配度越高。平局时返回第一个注册的手册。
        """
        query_lower = query.lower()
        best: tuple[int, SkillManual | None] = (0, None)

        for manual in self._manuals.values():
            score = sum(1 for kw in manual.keywords if kw.lower() in query_lower)
            if score > best[0]:
                best = (score, manual)

        return best[1] if best[0] > 0 else None

    def get_prompt_text(self, name_or_query: str) -> str | None:
        """获取手册内容作为 prompt 注入文本。支持按名称精确获取或按查询关键词匹配。"""
        manual = self.get(name_or_query) or self.match(name_or_query)
        if not manual:
            return None

        return f"""\
## 操作指南: {manual.name}

{manual.description}

以下是详细的操作流程和规范，请严格按照指南执行：

{manual.content}
"""

    # ── 内部 ────────────────────────────────────────────────

    def _parse_file(self, path: Path) -> SkillManual:
        text = path.read_text(encoding="utf-8")
        meta: dict[str, Any] = {}

        fm_match = _FRONTMATTER_RE.match(text)
        if fm_match:
            meta = yaml.safe_load(fm_match.group(1)) or {}
            content = text[fm_match.end():].strip()
        else:
            content = text

        return SkillManual(
            name=meta.get("name", path.stem),
            description=meta.get("description", ""),
            keywords=meta.get("keywords", []),
            content=content,
            source_path=str(path),
        )
