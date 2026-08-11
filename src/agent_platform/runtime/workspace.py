from __future__ import annotations

import hashlib
import re
from pathlib import Path

from agent_platform.runtime.models import RuntimeProfile

_SAFE_NAME_RE = re.compile(r"[^a-zA-Z0-9_.-]+")


class WorkspaceManager:
    """为每个 Skill/会话提供独立且不可路径穿越的持久工作目录。"""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def workspace_for(self, skill_name: str, session_id: str) -> Path:
        safe_skill = _SAFE_NAME_RE.sub("-", skill_name).strip("-.") or "skill"
        session_key = hashlib.sha256(session_id.encode("utf-8")).hexdigest()[:24]
        workspace = (self.root / safe_skill / session_key).resolve()
        if not workspace.is_relative_to(self.root):
            raise PermissionError("工作目录越界")
        workspace.mkdir(parents=True, exist_ok=True)
        return workspace

    @staticmethod
    def resolve(workspace: Path, relative_path: str) -> Path:
        requested = Path(relative_path)
        if requested.is_absolute():
            raise PermissionError("工作区工具不接受绝对路径")
        resolved = (workspace / requested).resolve()
        if not resolved.is_relative_to(workspace.resolve()):
            raise PermissionError("路径不在当前 Skill 工作区内")
        return resolved

    def write_text(
        self,
        workspace: Path,
        profile: RuntimeProfile,
        relative_path: str,
        content: str,
        *,
        overwrite: bool = False,
        max_bytes: int = 10 * 1024 * 1024,
    ) -> Path:
        path = self.resolve(workspace, relative_path)
        suffix = path.suffix.lower()
        if suffix not in profile.writable_suffixes:
            allowed = ", ".join(sorted(profile.writable_suffixes)) or "无"
            raise PermissionError(f"运行时 '{profile.name}' 不允许写入 {suffix or '无扩展名'}；允许: {allowed}")
        if path.exists() and not overwrite:
            raise FileExistsError(f"文件已存在: {relative_path}")
        payload = content.encode("utf-8")
        if len(payload) > max_bytes:
            raise ValueError(f"文件过大: {len(payload)} bytes")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        return path

    def read_text(self, workspace: Path, relative_path: str, *, max_chars: int = 50_000) -> str:
        path = self.resolve(workspace, relative_path)
        if not path.is_file():
            raise FileNotFoundError(f"文件不存在: {relative_path}")
        return path.read_text(encoding="utf-8")[:max_chars]

    def list_files(self, workspace: Path) -> list[str]:
        return [
            path.relative_to(workspace).as_posix()
            for path in sorted(workspace.rglob("*"))
            if path.is_file() and not path.is_symlink()
        ]
