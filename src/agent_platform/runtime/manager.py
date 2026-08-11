from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from agent_platform.config.settings import Settings
from agent_platform.runtime.artifacts import ArtifactStore
from agent_platform.runtime.context import SkillExecutionContext, activate_skill_context
from agent_platform.runtime.models import RuntimeProfile, RuntimeStatus
from agent_platform.runtime.sandbox import ContainerSandboxRunner
from agent_platform.runtime.workspace import WorkspaceManager


class SkillRuntimeManager:
    """服务端批准的 Runtime Profile 注册表和执行上下文工厂。"""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.workspace_manager = WorkspaceManager(settings.skill_workspace_root)
        self.artifact_store = ArtifactStore(
            settings.skill_artifact_root,
            ttl_seconds=settings.skill_artifact_ttl_seconds,
            max_bytes=settings.skill_artifact_max_bytes,
        )
        self.sandbox_runner = ContainerSandboxRunner(settings.skill_sandbox_engine)
        self._profiles = {
            "none": RuntimeProfile(name="none"),
            "cad-agentcad": RuntimeProfile(
                name="cad-agentcad",
                backend="container",
                enabled=settings.cad_skill_enabled,
                image=settings.cad_runtime_image,
                allowed_commands={
                    "agentcad": ("init", "run", "measure", "inspect", "diff", "export", "docs"),
                    "python": ("/opt/agent-platform/make_viewer.py",),
                },
                writable_suffixes=frozenset({".py", ".json", ".txt", ".md"}),
                timeout_seconds=settings.cad_runtime_timeout_seconds,
                memory_mb=settings.cad_runtime_memory_mb,
                cpus=settings.cad_runtime_cpus,
                pids_limit=settings.cad_runtime_pids_limit,
                network_enabled=False,
            ),
        }

    def get_profile(self, name: str | None) -> RuntimeProfile:
        profile_name = name or "none"
        profile = self._profiles.get(profile_name)
        if not profile:
            raise RuntimeError(f"未知 Runtime Profile: {profile_name}")
        return profile

    def validate_profile(self, name: str | None) -> None:
        self.get_profile(name)

    def status(self, name: str | None) -> RuntimeStatus:
        profile = self.get_profile(name)
        return self.sandbox_runner.status(profile)

    @contextmanager
    def execution(
        self,
        skill_name: str,
        runtime_profile: str | None,
        session_id: str,
    ) -> Iterator[SkillExecutionContext]:
        profile = self.get_profile(runtime_profile)
        status = self.sandbox_runner.status(profile)
        if not status.ready:
            raise RuntimeError(f"Skill Runtime '{profile.name}' 不可用: {status.reason}")
        workspace = self.workspace_manager.workspace_for(skill_name, session_id)
        context = SkillExecutionContext(
            skill_name=skill_name,
            session_id=session_id,
            profile=profile,
            workspace=workspace,
            workspace_manager=self.workspace_manager,
            sandbox_runner=self.sandbox_runner,
            artifact_store=self.artifact_store,
        )
        with activate_skill_context(context):
            yield context
