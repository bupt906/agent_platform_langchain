"""声明式 Skill 注册中心。

扫描 skills/ 目录，解析 SKILL.md 的 YAML frontmatter + Markdown body，
构建 DeclarativeSkill 对象供 builder 在运行时动态创建 LangGraph Agent。
"""

from __future__ import annotations

import logging
import re
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import yaml

SKILLS_DIR = Path(__file__).parent
logger = logging.getLogger(__name__)


@dataclass
class DeclarativeSkill:
    name: str
    description: str
    tools: list[str] = field(default_factory=list)
    body: str = ""
    complete_tool: str = "complete_task"
    runtime_profile: str | None = None
    source_dir: Path | None = None

    @property
    def references_dir(self) -> Path | None:
        if self.source_dir:
            return self.source_dir / "references"
        return None

    def load_reference(self, filename: str) -> str:
        if not self.references_dir:
            return ""
        ref_path = self.references_dir / filename
        if ref_path.exists():
            return ref_path.read_text(encoding="utf-8")
        return ""

    def load_all_references(self) -> dict[str, str]:
        refs: dict[str, str] = {}
        if not self.references_dir or not self.references_dir.exists():
            return refs
        for f in self.references_dir.rglob("*"):
            if f.is_file() and f.suffix in (".txt", ".md", ".yaml", ".yml", ".json"):
                rel = str(f.relative_to(self.references_dir))
                refs[rel] = f.read_text(encoding="utf-8")
        return refs

    @property
    def info(self) -> dict[str, object]:
        return {
            "name": self.name,
            "description": self.description,
            "tools": self.tools,
            "runtime_profile": self.runtime_profile,
        }


class DeclarativeSkillRegistry:
    """声明式 Skill 注册中心，扫描 skills/ 子目录下的 SKILL.md 文件。"""

    def __init__(
        self,
        skills_dir: str | Path | None = None,
        *,
        validator: Callable[[DeclarativeSkill], None] | None = None,
    ) -> None:
        self._skills_dir = Path(skills_dir) if skills_dir else SKILLS_DIR
        self._validator = validator
        self._skills: dict[str, DeclarativeSkill] = {}
        self._unavailable: dict[str, str] = {}
        self._lock = threading.RLock()
        self._source_signature: tuple[tuple[str, int, int], ...] = ()
        self._load_all()

    def _load_all(self) -> None:
        """完整加载 Skill；隔离配置错误，只发布校验通过的 Skill。"""
        with self._lock:
            loaded: dict[str, DeclarativeSkill] = {}
            unavailable: dict[str, str] = {}
            if self._skills_dir.exists():
                for skill_dir in sorted(self._skills_dir.iterdir()):
                    if not skill_dir.is_dir():
                        continue
                    skill_md = skill_dir / "SKILL.md"
                    if not skill_md.exists():
                        continue
                    skill = None
                    try:
                        skill = self._parse_file(skill_md, skill_dir)
                        if skill and self._validator:
                            self._validator(skill)
                    except RuntimeError as exc:
                        name = skill.name if skill else skill_dir.name
                        unavailable[name] = str(exc)
                        logger.error("声明式 Skill '%s' 配置无效，已禁用: %s", name, exc)
                        continue
                    if skill:
                        loaded[skill.name] = skill
            self._skills = loaded
            self._unavailable = unavailable
            self._source_signature = self._compute_source_signature()

    def _compute_source_signature(self) -> tuple[tuple[str, int, int], ...]:
        """记录所有 SKILL.md 的路径、修改时间和大小，用于轻量热刷新。"""
        if not self._skills_dir.exists():
            return ()
        signature = []
        for path in sorted(self._skills_dir.glob("*/SKILL.md")):
            stat = path.stat()
            signature.append((str(path), stat.st_mtime_ns, stat.st_size))
        return tuple(signature)

    def refresh_if_changed(self) -> bool:
        """SKILL.md 变化时原子重载，使 Markdown 修改无需重启 API。"""
        with self._lock:
            signature = self._compute_source_signature()
            if signature == self._source_signature:
                return False
            self._load_all()
            return True

    def _parse_file(self, md_path: Path, skill_dir: Path) -> DeclarativeSkill | None:
        content = md_path.read_text(encoding="utf-8")
        frontmatter, body = self._split_frontmatter(content)
        if not frontmatter:
            raise RuntimeError(f"{md_path}: 缺少有效的 YAML frontmatter")

        name = frontmatter.get("name", skill_dir.name)
        description = frontmatter.get("description", "")
        if not isinstance(name, str) or not name.strip():
            raise RuntimeError(f"{md_path}: 'name' 必须是非空字符串")
        if not isinstance(description, str):
            raise RuntimeError(f"{md_path}: 'description' 必须是字符串")
        if "tools" not in frontmatter:
            raise RuntimeError(
                f"{md_path}: YAML frontmatter 缺少顶层 'tools' 字段；请检查它是否被缩进到了 description 中"
            )
        tools_raw = frontmatter.get("tools", [])
        if not isinstance(tools_raw, (str, list)):
            raise RuntimeError(f"{md_path}: 'tools' 必须是列表或逗号分隔字符串")
        if isinstance(tools_raw, str):
            tools_raw = [t.strip() for t in tools_raw.strip("[]").split(",")]
        if any(not isinstance(tool, str) for tool in tools_raw):
            raise RuntimeError(f"{md_path}: 'tools' 中的每一项都必须是字符串")
        if any(not tool.strip().strip("'\"") for tool in tools_raw):
            raise RuntimeError(f"{md_path}: 'tools' 包含空工具名")
        tools = [tool.strip().strip("'\"") for tool in tools_raw]
        if len(tools) != len(set(tools)):
            raise RuntimeError(f"{md_path}: 'tools' 包含重复工具名")
        complete_tool = frontmatter.get("complete_tool", "complete_task")
        if not isinstance(complete_tool, str) or not complete_tool.strip():
            raise RuntimeError(f"{md_path}: 'complete_tool' 必须是非空字符串")
        runtime_profile = frontmatter.get("runtime")
        if runtime_profile is not None and (
            not isinstance(runtime_profile, str) or not runtime_profile.strip()
        ):
            raise RuntimeError(f"{md_path}: 'runtime' 必须是非空字符串")

        return DeclarativeSkill(
            name=name,
            description=description,
            tools=tools,
            body=body.strip(),
            complete_tool=complete_tool,
            runtime_profile=runtime_profile.strip() if runtime_profile else None,
            source_dir=skill_dir,
        )

    @staticmethod
    def _split_frontmatter(content: str) -> tuple[dict, str]:
        match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)", content, re.DOTALL)
        if not match:
            return {}, content
        try:
            fm = yaml.safe_load(match.group(1)) or {}
        except yaml.YAMLError:
            return {}, content
        if not isinstance(fm, dict):
            return {}, content
        return fm, match.group(2)

    def get(self, name: str) -> DeclarativeSkill | None:
        self.refresh_if_changed()
        with self._lock:
            return self._skills.get(name)

    def load(self, name: str) -> DeclarativeSkill:
        self.refresh_if_changed()
        with self._lock:
            skill = self._skills.get(name)
            unavailable_reason = self._unavailable.get(name)
        if unavailable_reason:
            raise RuntimeError(f"Skill '{name}' 不可用: {unavailable_reason}")
        if not skill:
            raise ValueError(f"Skill '{name}' not found. Available: {list(self._skills.keys())}")
        return skill

    def list_skills(self) -> list[DeclarativeSkill]:
        self.refresh_if_changed()
        with self._lock:
            return list(self._skills.values())

    def list_infos(self) -> list[dict[str, object]]:
        return [s.info for s in self.list_skills()]

    @property
    def unavailable_skills(self) -> dict[str, str]:
        """返回因配置错误而被隔离的 Skill 及原因。"""
        self.refresh_if_changed()
        with self._lock:
            return dict(self._unavailable)

    @property
    def count(self) -> int:
        self.refresh_if_changed()
        with self._lock:
            return len(self._skills)
