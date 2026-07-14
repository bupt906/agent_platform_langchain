"""项目范围内的受限命令执行工具。

工具名保留为 ``bash``，但实现刻意不启动 shell。命令会通过 ``shlex``
拆分后直接交给 ``subprocess``，因此不支持管道、重定向、命令替换或命令
串联。这足以运行项目自带 Python 脚本和测试，同时避免把任意 shell 权限
直接暴露给 Agent。
"""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

from langchain_core.tools import tool


_SHELL_OPERATORS = {
    "|",
    "||",
    "&",
    "&&",
    ";",
    ">",
    ">>",
    "<",
    "<<",
    "2>",
    "2>>",
}
_FORBIDDEN_EXECUTABLES = {
    "bash",
    "sh",
    "zsh",
    "fish",
    "sudo",
    "su",
    "rm",
    "dd",
    "mkfs",
    "chmod",
    "chown",
    "curl",
    "wget",
    "nc",
    "ncat",
    "netcat",
}
_PATH_SUFFIXES = {
    ".py",
    ".txt",
    ".md",
    ".json",
    ".csv",
    ".tsv",
    ".yaml",
    ".yml",
    ".xml",
    ".html",
    ".graphml",
    ".cypher",
    ".ttl",
}
_SECRET_ENV_RE = re.compile(r"(?:KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL)", re.IGNORECASE)
_FIND_FORBIDDEN_OPTIONS = {
    "-L",
    "-H",
    "-delete",
    "-exec",
    "-execdir",
    "-fls",
    "-fprint",
    "-fprint0",
    "-fprintf",
    "-ok",
    "-okdir",
}


def _result(**values) -> str:
    return json.dumps(values, ensure_ascii=False)


def _configured_values(value: str) -> set[str]:
    return {item.strip() for item in value.split(",") if item.strip()}


def _allowed_roots(configured_roots: str) -> list[Path]:
    return [Path(value).expanduser().resolve() for value in _configured_values(configured_roots)]


def _ensure_allowed_path(path: Path, configured_roots: str, label: str) -> Path:
    resolved = path.expanduser().resolve()
    roots = _allowed_roots(configured_roots)
    if not roots:
        raise PermissionError("未配置 bash 工具允许访问的目录")
    if not any(resolved.is_relative_to(root) for root in roots):
        allowed = ", ".join(str(root) for root in roots)
        raise PermissionError(f"{label}不在 bash 允许目录中: {resolved}。允许目录: {allowed}")
    return resolved


def _resolve_working_directory(working_directory: str, configured_roots: str) -> Path:
    path = Path(working_directory) if working_directory else Path.cwd()
    if not path.is_absolute():
        path = Path.cwd() / path
    resolved = _ensure_allowed_path(path, configured_roots, "工作目录")
    if not resolved.exists():
        raise FileNotFoundError(f"工作目录不存在: {working_directory or resolved}")
    if not resolved.is_dir():
        raise NotADirectoryError(f"工作目录不是目录: {resolved}")
    return resolved


def _parse_command(command: str) -> list[str]:
    if not command.strip():
        raise ValueError("command 不能为空")
    if "\n" in command or "\r" in command:
        raise ValueError("不允许多行命令")
    if "`" in command or "$(" in command or "${" in command:
        raise ValueError("不允许命令替换或环境变量展开")

    try:
        args = shlex.split(command, posix=True)
    except ValueError as exc:
        raise ValueError(f"命令解析失败: {exc}") from exc
    if not args:
        raise ValueError("command 不能为空")
    if any(token in _SHELL_OPERATORS for token in args):
        raise ValueError("不允许管道、重定向、后台执行或命令串联")
    return args


def _validate_executable(args: list[str], configured_commands: str) -> str:
    requested = args[0]
    executable_name = Path(requested).name
    if executable_name in _FORBIDDEN_EXECUTABLES:
        raise PermissionError(f"禁止执行命令: {executable_name}")

    allowed = _configured_values(configured_commands)
    if executable_name not in allowed:
        allowed_text = ", ".join(sorted(allowed)) or "（空）"
        raise PermissionError(f"命令 '{executable_name}' 不在白名单中。允许命令: {allowed_text}")

    # Python 的 -c/标准输入模式等价于任意代码执行。这里只允许文件脚本。
    if executable_name.startswith("python"):
        if "-c" in args[1:] or "-" in args[1:]:
            raise PermissionError("bash 工具不允许使用 Python -c 或标准输入执行代码")
        if "-m" in args[1:]:
            raise PermissionError("bash 工具不允许使用 Python -m；请直接调用白名单命令")

    if executable_name == "find":
        dangerous = _FIND_FORBIDDEN_OPTIONS.intersection(args[1:])
        if dangerous:
            raise PermissionError(
                f"bash 工具禁止 find 选项: {', '.join(sorted(dangerous))}"
            )
    if executable_name == "ls" and any(
        arg == "-L" or arg.startswith("--dereference") for arg in args[1:]
    ):
        raise PermissionError("bash 工具禁止 ls 解引用符号链接")

    executable = shutil.which(requested)
    if executable is None and executable_name in {"python", "python3"}:
        executable = sys.executable
    if executable is None:
        candidate = Path(requested).expanduser()
        if candidate.is_file() and os.access(candidate, os.X_OK):
            executable = str(candidate.resolve())
    if executable is None:
        raise FileNotFoundError(f"找不到可执行命令: {requested}")

    return executable


def _argument_path(token: str, cwd: Path) -> Path | None:
    if "://" in token:
        return None
    value = token.split("=", 1)[1] if token.startswith("--") and "=" in token else token
    if not value or value.startswith("-"):
        return None

    candidate = Path(value).expanduser()
    looks_like_path = (
        candidate.is_absolute()
        or value.startswith((".", "~"))
        or "/" in value
        or "\\" in value
        or candidate.suffix.lower() in _PATH_SUFFIXES
        or (cwd / candidate).exists()
    )
    if not looks_like_path:
        return None
    return candidate if candidate.is_absolute() else cwd / candidate


def _validate_argument_paths(args: list[str], cwd: Path, configured_roots: str) -> None:
    for token in args[1:]:
        candidate = _argument_path(token, cwd)
        if candidate is not None:
            _ensure_allowed_path(candidate, configured_roots, "命令参数路径")


def _safe_environment() -> dict[str, str]:
    """传递运行所需的基础环境，但不把密钥类变量暴露给子进程。"""
    keep = {
        "HOME",
        "LANG",
        "LC_ALL",
        "PATH",
        "PYTHONPATH",
        "VIRTUAL_ENV",
        "SYSTEMROOT",
        "TMP",
        "TEMP",
        "TMPDIR",
    }
    return {
        key: value
        for key, value in os.environ.items()
        if key in keep and not _SECRET_ENV_RE.search(key)
    }


def _truncate_output(value: str, max_chars: int) -> tuple[str, bool]:
    if max_chars <= 0 or len(value) <= max_chars:
        return value, False
    head_chars = max_chars * 2 // 3
    tail_chars = max_chars - head_chars
    omitted = len(value) - max_chars
    truncated = (
        value[:head_chars]
        + f"\n\n... truncated ({omitted} chars omitted) ...\n\n"
        + value[-tail_chars:]
    )
    return truncated, True


@tool("bash")
def bash(
    command: str,
    working_directory: str = "",
    timeout: int = 0,
) -> str:
    """在项目允许目录中执行一条白名单命令，并返回结构化结果。

    适合运行项目自带 Python 脚本、pytest 和 ruff。命令不会经过 shell，
    因此不支持 ``|``、``>``, ``&&``、``;``、命令替换或多行命令。

    Args:
        command: 单条命令字符串，例如 ``python scripts/build.py --out output.json``。
        working_directory: 工作目录；默认使用服务进程当前目录。
        timeout: 超时秒数；0 表示使用系统默认值。
    """
    from agent_platform.config.settings import settings

    try:
        effective_timeout = timeout or settings.bash_default_timeout_seconds
        if effective_timeout <= 0:
            raise ValueError("timeout 必须大于 0")
        if effective_timeout > settings.bash_max_timeout_seconds:
            raise ValueError(f"timeout 不能超过 {settings.bash_max_timeout_seconds} 秒")

        cwd = _resolve_working_directory(working_directory, settings.bash_allowed_roots)
        args = _parse_command(command)
        executable = _validate_executable(args, settings.bash_allowed_commands)
        args[0] = executable
        _validate_argument_paths(args, cwd, settings.bash_allowed_roots)

        completed = subprocess.run(
            args,
            cwd=cwd,
            env=_safe_environment(),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=effective_timeout,
            check=False,
        )
        stdout, stdout_truncated = _truncate_output(
            completed.stdout,
            settings.bash_max_output_chars,
        )
        stderr, stderr_truncated = _truncate_output(
            completed.stderr,
            settings.bash_max_output_chars,
        )
        return _result(
            success=completed.returncode == 0,
            command=command,
            cwd=str(cwd),
            exit_code=completed.returncode,
            stdout=stdout,
            stderr=stderr,
            truncated=stdout_truncated or stderr_truncated,
            timed_out=False,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout.decode("utf-8", errors="replace") if isinstance(exc.stdout, bytes) else exc.stdout or ""
        stderr = exc.stderr.decode("utf-8", errors="replace") if isinstance(exc.stderr, bytes) else exc.stderr or ""
        return _result(
            success=False,
            command=command,
            error=f"TimeoutExpired: 命令执行超过 {timeout or settings.bash_default_timeout_seconds} 秒",
            stdout=stdout,
            stderr=stderr,
            timed_out=True,
        )
    except Exception as exc:
        return _result(
            success=False,
            command=command,
            error=f"{type(exc).__name__}: {exc}",
            timed_out=False,
        )


def register_bash_tool() -> None:
    from agent_platform.tools.registry import register

    register(bash)
