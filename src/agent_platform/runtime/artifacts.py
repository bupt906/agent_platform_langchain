from __future__ import annotations

import json
import re
import secrets
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

from agent_platform.runtime.models import ArtifactRecord

_ARTIFACT_ID_RE = re.compile(r"^[A-Za-z0-9_-]{20,80}$")
_SAFE_MEDIA_TYPES = {
    ".html": "text/html",
    ".glb": "model/gltf-binary",
    ".gltf": "model/gltf+json",
    ".stl": "model/stl",
    ".step": "model/step",
    ".stp": "model/step",
    ".obj": "model/obj",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".json": "application/json",
    ".csv": "text/csv",
    ".txt": "text/plain",
}


class ArtifactStore:
    """基于共享文件系统的制品仓库；ID 可跨进程和重启解析。"""

    def __init__(self, root: str | Path, *, ttl_seconds: int, max_bytes: int) -> None:
        self.root = Path(root).expanduser().resolve()
        self.ttl_seconds = ttl_seconds
        self.max_bytes = max_bytes
        self.root.mkdir(parents=True, exist_ok=True)

    def publish(self, source: Path, workspace: Path, *, display_name: str = "") -> ArtifactRecord:
        resolved = source.resolve()
        if not resolved.is_relative_to(workspace.resolve()) or not resolved.is_file():
            raise PermissionError("只能发布当前 Skill 工作区内的文件")
        size = resolved.stat().st_size
        if size > self.max_bytes:
            raise ValueError(f"制品过大: {size} bytes，最大 {self.max_bytes} bytes")
        media_type = _SAFE_MEDIA_TYPES.get(resolved.suffix.lower())
        if not media_type:
            raise ValueError(f"不支持的制品类型: {resolved.suffix}")

        artifact_id = secrets.token_urlsafe(24)
        artifact_dir = self.root / artifact_id
        artifact_dir.mkdir(mode=0o700)
        safe_name = Path(display_name or resolved.name).name
        if safe_name in {"", ".", ".."}:
            raise ValueError("制品显示名称无效")
        storage_name = f"payload{resolved.suffix.lower()}"
        payload_path = artifact_dir / storage_name
        shutil.copyfile(resolved, payload_path)
        created_at = datetime.now(timezone.utc).isoformat()
        metadata = {
            "artifact_id": artifact_id,
            "name": safe_name,
            "storage_name": storage_name,
            "media_type": media_type,
            "size_bytes": size,
            "created_at": created_at,
        }
        (artifact_dir / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False), encoding="utf-8")
        return ArtifactRecord(
            artifact_id=artifact_id,
            name=safe_name,
            media_type=media_type,
            path=payload_path,
            size_bytes=size,
            created_at=created_at,
        )

    def get(self, artifact_id: str) -> ArtifactRecord | None:
        if not _ARTIFACT_ID_RE.fullmatch(artifact_id):
            return None
        artifact_dir = (self.root / artifact_id).resolve()
        if not artifact_dir.is_relative_to(self.root):
            return None
        metadata_path = artifact_dir / "metadata.json"
        if not metadata_path.is_file():
            return None
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            created = datetime.fromisoformat(metadata["created_at"])
            if self.ttl_seconds > 0 and datetime.now(timezone.utc) - created > timedelta(seconds=self.ttl_seconds):
                return None
            storage_name = Path(metadata.get("storage_name") or metadata["name"]).name
            payload_path = (artifact_dir / storage_name).resolve()
            if not payload_path.is_relative_to(artifact_dir) or not payload_path.is_file():
                return None
            return ArtifactRecord(
                artifact_id=metadata["artifact_id"],
                name=metadata["name"],
                media_type=metadata["media_type"],
                path=payload_path,
                size_bytes=metadata["size_bytes"],
                created_at=metadata["created_at"],
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            return None

    def cleanup_expired(self) -> int:
        removed = 0
        for artifact_dir in self.root.iterdir():
            if not artifact_dir.is_dir():
                continue
            if self.get(artifact_dir.name) is None:
                shutil.rmtree(artifact_dir, ignore_errors=True)
                removed += 1
        return removed
