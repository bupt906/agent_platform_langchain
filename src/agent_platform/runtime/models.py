from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


@dataclass(frozen=True)
class RuntimeStatus:
    ready: bool
    profile: str
    backend: str
    reason: str | None = None
    image: str | None = None


@dataclass(frozen=True)
class RuntimeProfile:
    name: str
    backend: Literal["none", "container"] = "none"
    enabled: bool = True
    image: str = ""
    allowed_commands: dict[str, tuple[str, ...]] = field(default_factory=dict)
    writable_suffixes: frozenset[str] = frozenset()
    timeout_seconds: int = 120
    memory_mb: int = 512
    cpus: float = 1.0
    pids_limit: int = 32
    network_enabled: bool = False


@dataclass(frozen=True)
class SandboxResult:
    success: bool
    command: str
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    error: str | None = None
    timed_out: bool = False
    truncated: bool = False


@dataclass(frozen=True)
class ArtifactRecord:
    artifact_id: str
    name: str
    media_type: str
    path: Path
    size_bytes: int
    created_at: str
