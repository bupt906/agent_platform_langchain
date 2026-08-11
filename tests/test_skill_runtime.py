from __future__ import annotations

import json
import subprocess
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agent_platform.api.routes import artifacts
from agent_platform.api.routes.chat import _extract_artifact, _resolve_single_target
from agent_platform.config.settings import Settings
from agent_platform.runtime import SkillRuntimeManager
from agent_platform.runtime.artifacts import ArtifactStore
from agent_platform.runtime.context import SkillExecutionContext, activate_skill_context
from agent_platform.runtime.models import RuntimeProfile
from agent_platform.runtime.sandbox import ContainerSandboxRunner
from agent_platform.runtime.workspace import WorkspaceManager
from agent_platform.skills.registry import DeclarativeSkillRegistry
from agent_platform.tools import register_all_declarative_tools
from agent_platform.tools.file_tools import read_file, write_file
from agent_platform.tools.registry import tool_map
from agent_platform.tools.runtime_tools import publish_artifact, workspace_write


def test_workspace_blocks_traversal_and_enforces_suffixes(tmp_path) -> None:
    manager = WorkspaceManager(tmp_path / "workspaces")
    workspace = manager.workspace_for("cad-agentcad", "session-a")
    profile = RuntimeProfile(name="cad", writable_suffixes=frozenset({".py"}))

    written = manager.write_text(workspace, profile, "model.py", "show_object(Box(1, 1, 1))")

    assert written.is_file()
    with pytest.raises(PermissionError):
        manager.resolve(workspace, "../outside.py")
    with pytest.raises(PermissionError):
        manager.write_text(workspace, profile, "payload.sh", "echo unsafe")


def test_global_file_tools_can_read_but_not_create_python(tmp_path, monkeypatch) -> None:
    from agent_platform.config.settings import settings

    script = tmp_path / "existing.py"
    script.write_text("print('trusted project script')", encoding="utf-8")
    monkeypatch.setattr(settings, "file_read_allowed_roots", str(tmp_path))
    monkeypatch.setattr(settings, "file_write_allowed_roots", str(tmp_path))

    assert json.loads(read_file.func(str(script)))["success"] is True
    denied = json.loads(write_file.func(str(tmp_path / "generated.py"), "print('unsafe')"))
    assert denied["success"] is False
    assert "不支持的文件类型" in denied["error"]


def test_runtime_profile_rejects_unapproved_commands() -> None:
    profile = RuntimeProfile(
        name="cad",
        backend="container",
        allowed_commands={
            "agentcad": ("run", "measure"),
            "python": ("/opt/agent-platform/make_viewer.py",),
        },
    )

    assert ContainerSandboxRunner.validate_command(profile, "agentcad run model.py") == [
        "agentcad",
        "run",
        "model.py",
    ]
    with pytest.raises(PermissionError):
        ContainerSandboxRunner.validate_command(profile, "sh -c id")
    with pytest.raises(PermissionError):
        ContainerSandboxRunner.validate_command(profile, "python model.py")
    with pytest.raises(PermissionError):
        ContainerSandboxRunner.validate_command(profile, "agentcad view output.step")


def test_runtime_status_preserves_engine_failure_reason(monkeypatch) -> None:
    runner = ContainerSandboxRunner("docker")
    profile = RuntimeProfile(name="cad", backend="container", image="cad:test")
    monkeypatch.setattr("agent_platform.runtime.sandbox.shutil.which", lambda _name: "/usr/bin/docker")
    monkeypatch.setattr(
        "agent_platform.runtime.sandbox.subprocess.run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess([], 1, "", "permission denied"),
    )

    status = runner.status(profile)

    assert status.ready is False
    assert status.reason == "sandbox_engine_unavailable: permission denied"


def test_runtime_tools_require_context_and_publish_persistent_artifact(tmp_path) -> None:
    workspace_manager = WorkspaceManager(tmp_path / "workspaces")
    artifact_store = ArtifactStore(tmp_path / "artifacts", ttl_seconds=3600, max_bytes=1024)
    workspace = workspace_manager.workspace_for("cad-agentcad", "session-a")
    profile = RuntimeProfile(name="cad", writable_suffixes=frozenset({".html"}))
    context = SkillExecutionContext(
        skill_name="cad-agentcad",
        session_id="session-a",
        profile=profile,
        workspace=workspace,
        workspace_manager=workspace_manager,
        sandbox_runner=ContainerSandboxRunner("missing-engine"),
        artifact_store=artifact_store,
    )

    assert json.loads(workspace_write.func("viewer.html", "<html>safe</html>"))["success"] is False
    with activate_skill_context(context):
        assert json.loads(workspace_write.func("viewer.html", "<html>safe</html>"))["success"] is True
        published = json.loads(publish_artifact.func("viewer.html", "viewer.html"))

    assert published["success"] is True
    reopened = ArtifactStore(tmp_path / "artifacts", ttl_seconds=3600, max_bytes=1024)
    assert reopened.get(published["artifact_id"]) is not None


def test_artifact_display_name_cannot_overwrite_metadata(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    source = workspace / "viewer.html"
    source.write_text("<html>safe</html>", encoding="utf-8")
    store = ArtifactStore(tmp_path / "artifacts", ttl_seconds=3600, max_bytes=1024)

    record = store.publish(source, workspace, display_name="metadata.json")
    reopened = store.get(record.artifact_id)

    assert reopened is not None
    assert reopened.name == "metadata.json"
    assert reopened.path.name == "payload.html"
    assert reopened.path.read_text(encoding="utf-8") == "<html>safe</html>"


def test_artifact_route_sets_html_security_headers(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    source = workspace / "viewer.html"
    source.write_text("<script>document.body.textContent='ok'</script>", encoding="utf-8")
    store = ArtifactStore(tmp_path / "artifacts", ttl_seconds=3600, max_bytes=4096)
    record = store.publish(source, workspace)
    app = FastAPI()
    app.state.deps = SimpleNamespace(artifact_store=store)
    app.include_router(artifacts.router)

    response = TestClient(app).get(f"/artifacts/{record.artifact_id}")

    assert response.status_code == 200
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "sandbox allow-scripts" in response.headers["content-security-policy"]
    assert "connect-src 'none'" in response.headers["content-security-policy"]


def test_cad_skill_uses_isolated_runtime_tools(tmp_path) -> None:
    register_all_declarative_tools()
    registry = DeclarativeSkillRegistry()
    cad = registry.load("cad-agentcad")

    assert cad.runtime_profile == "cad-agentcad"
    assert set(cad.tools) == {
        "workspace_read",
        "workspace_write",
        "workspace_list",
        "sandbox_run",
        "publish_artifact",
    }
    assert set(cad.tools).issubset(tool_map())
    assert "bash" not in cad.tools
    assert "write_file" not in cad.tools


def test_unready_runtime_falls_back_before_model_execution(tmp_path, deps) -> None:
    settings = Settings(
        skill_workspace_root=tmp_path / "workspaces",
        skill_artifact_root=tmp_path / "artifacts",
        skill_sandbox_engine="definitely-missing-engine",
    )
    deps.runtime_manager = SkillRuntimeManager(settings)
    deps.declarative_registry = DeclarativeSkillRegistry()

    target = _resolve_single_target(deps, "cad-agentcad", explicit_mode="skill")

    assert target.target_type == "general"
    assert target.requested_skill == "cad-agentcad"
    assert "sandbox_engine_not_found" in (target.fallback_reason or "")


def test_publish_artifact_event_exposes_only_public_metadata() -> None:
    result = _extract_artifact(
        {
            "event": "on_tool_end",
            "name": "publish_artifact",
            "data": {
                "output": json.dumps(
                    {
                        "success": True,
                        "artifact_id": "safe-id",
                        "name": "viewer.html",
                        "media_type": "text/html",
                        "size_bytes": 42,
                        "path": "/private/workspace/viewer.html",
                    }
                )
            },
        }
    )

    assert result == {
        "artifact_id": "safe-id",
        "name": "viewer.html",
        "media_type": "text/html",
        "size_bytes": 42,
    }
