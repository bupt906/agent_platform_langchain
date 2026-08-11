from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from agent_platform.runtime.artifacts import ArtifactStore
from agent_platform.runtime.models import RuntimeProfile
from agent_platform.runtime.sandbox import ContainerSandboxRunner
from agent_platform.runtime.workspace import WorkspaceManager


@dataclass(frozen=True)
class SkillExecutionContext:
    skill_name: str
    session_id: str
    profile: RuntimeProfile
    workspace: Path
    workspace_manager: WorkspaceManager
    sandbox_runner: ContainerSandboxRunner
    artifact_store: ArtifactStore


_current_context: ContextVar[SkillExecutionContext | None] = ContextVar(
    "skill_execution_context",
    default=None,
)


def current_skill_context() -> SkillExecutionContext:
    context = _current_context.get()
    if context is None:
        raise RuntimeError("当前工具调用不在受管 Skill 执行上下文中")
    return context


@contextmanager
def activate_skill_context(context: SkillExecutionContext) -> Iterator[SkillExecutionContext]:
    token = _current_context.set(context)
    try:
        yield context
    finally:
        _current_context.reset(token)
