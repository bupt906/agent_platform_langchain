from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import time
import uuid
from pathlib import Path

from agent_platform.runtime.models import RuntimeProfile, RuntimeStatus, SandboxResult


def _truncate(value: str, max_chars: int = 15_000) -> tuple[str, bool]:
    if len(value) <= max_chars:
        return value, False
    return value[:10_000] + "\n... truncated ...\n" + value[-5_000:], True


class ContainerSandboxRunner:
    """通过 Docker/Podman 在无网络、只读根文件系统中执行模型生成代码。"""

    def __init__(self, engine: str = "docker") -> None:
        self.engine = engine
        self._status_cache: dict[str, tuple[float, RuntimeStatus]] = {}

    def status(self, profile: RuntimeProfile) -> RuntimeStatus:
        if not profile.enabled:
            return RuntimeStatus(False, profile.name, profile.backend, "runtime_disabled", profile.image or None)
        if profile.backend == "none":
            return RuntimeStatus(True, profile.name, profile.backend)
        cached = self._status_cache.get(profile.name)
        if cached and time.monotonic() - cached[0] < 5:
            return cached[1]
        engine_path = shutil.which(self.engine)
        if not engine_path:
            status = RuntimeStatus(False, profile.name, profile.backend, f"sandbox_engine_not_found: {self.engine}", profile.image)
        elif not profile.image:
            status = RuntimeStatus(False, profile.name, profile.backend, "runtime_image_not_configured")
        else:
            try:
                probe = subprocess.run(
                    [engine_path, "image", "inspect", profile.image],
                    stdin=subprocess.DEVNULL,
                    capture_output=True,
                    text=True,
                    timeout=5,
                    check=False,
                )
                if probe.returncode == 0:
                    reason = None
                elif "no such image" in probe.stderr.lower():
                    reason = f"runtime_image_not_found: {profile.image}"
                else:
                    detail = " ".join(probe.stderr.strip().split())[:500] or f"exit_code={probe.returncode}"
                    reason = f"sandbox_engine_unavailable: {detail}"
                status = RuntimeStatus(probe.returncode == 0, profile.name, profile.backend, reason, profile.image)
            except (OSError, subprocess.TimeoutExpired) as exc:
                status = RuntimeStatus(False, profile.name, profile.backend, f"runtime_probe_failed: {exc}", profile.image)
        self._status_cache[profile.name] = (time.monotonic(), status)
        return status

    @staticmethod
    def validate_command(profile: RuntimeProfile, command: str) -> list[str]:
        try:
            args = shlex.split(command, posix=True)
        except ValueError as exc:
            raise ValueError(f"命令解析失败: {exc}") from exc
        if not args:
            raise ValueError("命令不能为空")
        executable = Path(args[0]).name
        allowed_subcommands = profile.allowed_commands.get(executable)
        if allowed_subcommands is None:
            raise PermissionError(f"运行时 '{profile.name}' 不允许命令: {executable}")
        if executable == "python":
            if len(args) < 2 or args[1] not in allowed_subcommands:
                raise PermissionError("python 只允许执行运行时内置的审核脚本")
        elif allowed_subcommands and (len(args) < 2 or args[1] not in allowed_subcommands):
            raise PermissionError(f"命令 '{executable}' 不允许子命令: {args[1] if len(args) > 1 else '（空）'}")
        return args

    def run(
        self,
        profile: RuntimeProfile,
        workspace: Path,
        command: str,
        *,
        timeout: int = 0,
    ) -> SandboxResult:
        container_name = f"agent-platform-{uuid.uuid4().hex[:20]}"
        engine_path: str | None = None
        status = self.status(profile)
        if not status.ready:
            return SandboxResult(False, command, error=status.reason)
        if profile.backend != "container":
            return SandboxResult(False, command, error="该运行时不支持命令执行")
        try:
            args = self.validate_command(profile, command)
            effective_timeout = timeout or profile.timeout_seconds
            if effective_timeout <= 0 or effective_timeout > profile.timeout_seconds:
                raise ValueError(f"timeout 必须在 1..{profile.timeout_seconds} 秒之间")
            engine_path = shutil.which(self.engine)
            if not engine_path:
                raise FileNotFoundError(f"找不到沙箱引擎: {self.engine}")
            uid = os.getuid() if hasattr(os, "getuid") else 65532
            gid = os.getgid() if hasattr(os, "getgid") else 65532
            docker_args = [
                engine_path,
                "run",
                "--rm",
                "--name",
                container_name,
                "--network",
                "none" if not profile.network_enabled else "bridge",
                "--read-only",
                "--cap-drop",
                "ALL",
                "--security-opt",
                "no-new-privileges",
                "--pids-limit",
                str(profile.pids_limit),
                "--memory",
                f"{profile.memory_mb}m",
                "--cpus",
                str(profile.cpus),
                "--user",
                f"{uid}:{gid}",
                "--tmpfs",
                "/tmp:rw,nosuid,nodev,size=64m",
                "--mount",
                f"type=bind,src={workspace},dst=/workspace,rw",
                "--workdir",
                "/workspace",
                "--env",
                "HOME=/tmp",
                "--env",
                "PYTHONUTF8=1",
                profile.image,
                *args,
            ]
            completed = subprocess.run(
                docker_args,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=effective_timeout,
                check=False,
            )
            stdout, out_truncated = _truncate(completed.stdout)
            stderr, err_truncated = _truncate(completed.stderr)
            return SandboxResult(
                completed.returncode == 0,
                command,
                exit_code=completed.returncode,
                stdout=stdout,
                stderr=stderr,
                truncated=out_truncated or err_truncated,
            )
        except subprocess.TimeoutExpired as exc:
            if engine_path:
                subprocess.run(
                    [engine_path, "rm", "--force", container_name],
                    stdin=subprocess.DEVNULL,
                    capture_output=True,
                    timeout=10,
                    check=False,
                )
            return SandboxResult(False, command, error=f"TimeoutExpired: {exc}", timed_out=True)
        except Exception as exc:
            return SandboxResult(False, command, error=f"{type(exc).__name__}: {exc}")
