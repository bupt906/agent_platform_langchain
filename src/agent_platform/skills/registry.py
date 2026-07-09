"""声明式 Skill 注册中心。

扫描 skills/ 目录，解析 SKILL.md 的 YAML frontmatter + Markdown body，
构建 DeclarativeSkill 对象供 builder 在运行时动态创建 LangGraph Agent。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

SKILLS_DIR = Path(__file__).parent


@dataclass
class DeclarativeSkill:
    name: str
    description: str
    tools: list[str] = field(default_factory=list)
    body: str = ""
    complete_tool: str = "complete_task"
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
        }


class DeclarativeSkillRegistry:
    """声明式 Skill 注册中心，扫描 skills/ 子目录下的 SKILL.md 文件。"""

    def __init__(self, skills_dir: str | Path | None = None) -> None:
        self._skills_dir = Path(skills_dir) if skills_dir else SKILLS_DIR
        self._skills: dict[str, DeclarativeSkill] = {}
        self._load_all()

    def _load_all(self) -> None:
        if not self._skills_dir.exists():
            return
        for skill_dir in sorted(self._skills_dir.iterdir()):
            if not skill_dir.is_dir():
                continue
            skill_md = skill_dir / "SKILL.md"
            if not skill_md.exists():
                continue
            skill = self._parse_file(skill_md, skill_dir)
            if skill:
                self._skills[skill.name] = skill

    def _parse_file(self, md_path: Path, skill_dir: Path) -> DeclarativeSkill | None:
        content = md_path.read_text(encoding="utf-8")
        frontmatter, body = self._split_frontmatter(content)
        if not frontmatter:
            return None

        name = frontmatter.get("name", skill_dir.name)
        description = frontmatter.get("description", "")
        tools_raw = frontmatter.get("tools", [])
        if isinstance(tools_raw, str):
            tools_raw = [t.strip() for t in tools_raw.strip("[]").split(",")]
        tools = [t.strip().strip("'\"") for t in tools_raw if t.strip()]
        complete_tool = frontmatter.get("complete_tool", "complete_task")

        return DeclarativeSkill(
            name=name,
            description=description,
            tools=tools,
            body=body.strip(),
            complete_tool=complete_tool,
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
        return fm, match.group(2)

    def get(self, name: str) -> DeclarativeSkill | None:
        return self._skills.get(name)

    def load(self, name: str) -> DeclarativeSkill:
        skill = self._skills.get(name)
        if not skill:
            raise ValueError(f"Skill '{name}' not found. Available: {list(self._skills.keys())}")
        return skill

    def list_skills(self) -> list[DeclarativeSkill]:
        return list(self._skills.values())

    def list_infos(self) -> list[dict[str, object]]:
        return [s.info for s in self._skills.values()]

    @property
    def count(self) -> int:
        return len(self._skills)
