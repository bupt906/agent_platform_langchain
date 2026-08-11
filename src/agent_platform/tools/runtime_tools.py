from __future__ import annotations

import json

from langchain_core.tools import tool

from agent_platform.runtime.context import current_skill_context


def _result(**values) -> str:
    return json.dumps(values, ensure_ascii=False)


@tool
def workspace_write(
    file_path: str,
    content: str,
    overwrite: bool = False,
) -> str:
    """在当前 Skill 的隔离工作区写入文本文件。路径必须是相对路径。"""
    try:
        context = current_skill_context()
        path = context.workspace_manager.write_text(
            context.workspace,
            context.profile,
            file_path,
            content,
            overwrite=overwrite,
        )
        return _result(
            success=True,
            path=path.relative_to(context.workspace).as_posix(),
            bytes_written=len(content.encode("utf-8")),
        )
    except Exception as exc:
        return _result(success=False, error=f"{type(exc).__name__}: {exc}", file_path=file_path)


@tool
def workspace_read(file_path: str, max_chars: int = 50_000) -> str:
    """读取当前 Skill 隔离工作区中的 UTF-8 文本文件。"""
    try:
        context = current_skill_context()
        content = context.workspace_manager.read_text(context.workspace, file_path, max_chars=max_chars)
        return _result(success=True, path=file_path, content=content, truncated=len(content) >= max_chars)
    except Exception as exc:
        return _result(success=False, error=f"{type(exc).__name__}: {exc}", file_path=file_path)


@tool
def workspace_list() -> str:
    """列出当前 Skill 隔离工作区内的文件。"""
    try:
        context = current_skill_context()
        return _result(success=True, files=context.workspace_manager.list_files(context.workspace))
    except Exception as exc:
        return _result(success=False, error=f"{type(exc).__name__}: {exc}")


@tool
def sandbox_run(command: str, timeout: int = 0) -> str:
    """使用当前 Skill 已批准的 Runtime Profile 在隔离容器中执行命令。"""
    try:
        context = current_skill_context()
        result = context.sandbox_runner.run(
            context.profile,
            context.workspace,
            command,
            timeout=timeout,
        )
        return _result(**result.__dict__)
    except Exception as exc:
        return _result(success=False, command=command, error=f"{type(exc).__name__}: {exc}")


@tool
def publish_artifact(file_path: str, display_name: str = "") -> str:
    """发布当前 Skill 工作区内的输出文件，返回跨进程可访问的 artifact_id。"""
    try:
        context = current_skill_context()
        source = context.workspace_manager.resolve(context.workspace, file_path)
        record = context.artifact_store.publish(
            source,
            context.workspace,
            display_name=display_name,
        )
        return _result(
            success=True,
            artifact_id=record.artifact_id,
            name=record.name,
            media_type=record.media_type,
            size_bytes=record.size_bytes,
        )
    except Exception as exc:
        return _result(success=False, error=f"{type(exc).__name__}: {exc}", file_path=file_path)


def register_runtime_tools() -> None:
    from agent_platform.tools.registry import register

    for runtime_tool in (workspace_write, workspace_read, workspace_list, sandbox_run, publish_artifact):
        register(runtime_tool)
