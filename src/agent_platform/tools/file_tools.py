"""受限的文本文件读写工具。"""

from __future__ import annotations

import json
from pathlib import Path

from langchain_core.tools import tool


TEXT_SUFFIXES = {
    ".txt",
    ".md",
    ".markdown",
    ".json",
    ".csv",
    ".tsv",
    ".yaml",
    ".yml",
    ".xml",
    ".html",
    ".htm",
    ".log",
    ".graphml",
    ".cypher",
    ".ttl",
}
SUPPORTED_ENCODINGS = ("utf-8", "utf-8-sig", "gb18030")


def _result(**values) -> str:
    return json.dumps(values, ensure_ascii=False)


def _allowed_roots(configured_roots: str) -> list[Path]:
    roots: list[Path] = []
    for value in configured_roots.split(","):
        value = value.strip()
        if value:
            roots.append(Path(value).expanduser().resolve())
    return roots


def _ensure_path_in_allowed_roots(
    path: Path,
    configured_roots: str,
    operation: str,
) -> None:
    """确保解析后的路径处于当前配置允许的目录范围内。"""
    roots = _allowed_roots(configured_roots)
    if not roots:
        raise PermissionError(f"未配置允许{operation}的目录")
    if not any(path.is_relative_to(root) for root in roots):
        allowed = ", ".join(str(root) for root in roots)
        raise PermissionError(f"文件不在允许{operation}的目录中。允许目录: {allowed}")


def _resolve_allowed_path(
    file_path: str,
    configured_roots: str,
    operation: str,
) -> Path:
    requested = Path(file_path).expanduser()
    if not requested.is_absolute():
        requested = Path.cwd() / requested
    resolved = requested.resolve()
    _ensure_path_in_allowed_roots(resolved, configured_roots, operation)
    return resolved


def _decode_text(raw: bytes, encoding: str) -> tuple[str, str]:
    if encoding != "auto":
        if encoding not in SUPPORTED_ENCODINGS:
            raise ValueError(
                f"不支持编码 '{encoding}'，可用值: auto, {', '.join(SUPPORTED_ENCODINGS)}"
            )
        return raw.decode(encoding), encoding

    errors: list[str] = []
    candidates = ("utf-8-sig", "gb18030") if raw.startswith(b"\xef\xbb\xbf") else ("utf-8", "gb18030")
    for candidate in candidates:
        try:
            return raw.decode(candidate), candidate
        except UnicodeDecodeError as exc:
            errors.append(f"{candidate}: {exc}")
    raise UnicodeDecodeError("auto", raw, 0, len(raw), "; ".join(errors))


@tool
def read_file(
    file_path: str,
    offset: int = 0,
    limit: int = 20_000,
    encoding: str = "auto",
) -> str:
    """读取允许目录内的文本文件，并以 JSON 返回内容和分页信息。

    Args:
        file_path: 文件路径。相对路径以服务进程的当前工作目录为基准。
        offset: 从第几个字符开始读取，默认 0。
        limit: 最多返回的字符数，默认 20000，且不能超过系统配置上限。
        encoding: auto、utf-8-sig、utf-8 或 gb18030，默认自动识别。

    返回中的 truncated 表示内容是否被截断；若为 true，可将 next_offset
    作为下一次调用的 offset 继续读取。
    """
    from agent_platform.config.settings import settings

    try:
        if offset < 0:
            raise ValueError("offset 不能小于 0")
        if limit <= 0:
            raise ValueError("limit 必须大于 0")
        if limit > settings.file_read_max_chars:
            raise ValueError(f"limit 不能超过 {settings.file_read_max_chars}")

        path = _resolve_allowed_path(
            file_path,
            settings.file_read_allowed_roots,
            "读取",
        )
        if not path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")
        if not path.is_file():
            raise ValueError(f"路径不是文件: {file_path}")
        if path.suffix.lower() not in TEXT_SUFFIXES:
            supported = ", ".join(sorted(TEXT_SUFFIXES))
            raise ValueError(f"不支持的文件类型 '{path.suffix}'。支持: {supported}")

        size = path.stat().st_size
        if size > settings.file_read_max_bytes:
            raise ValueError(
                f"文件过大: {size} bytes，最大允许 {settings.file_read_max_bytes} bytes"
            )

        raw = path.read_bytes()
        if b"\x00" in raw:
            raise ValueError("文件包含 NUL 字节，可能不是文本文件")
        text, detected_encoding = _decode_text(raw, encoding)
        total_chars = len(text)
        content = text[offset : offset + limit]
        next_offset = offset + len(content)
        truncated = next_offset < total_chars

        return _result(
            success=True,
            path=str(path),
            encoding=detected_encoding,
            offset=offset,
            chars_returned=len(content),
            total_chars=total_chars,
            truncated=truncated,
            next_offset=next_offset if truncated else None,
            content=content,
        )
    except Exception as exc:
        return _result(
            success=False,
            error=f"{type(exc).__name__}: {exc}",
            file_path=file_path,
        )


@tool
def write_file(
    file_path: str,
    content: str,
    encoding: str = "utf-8",
    overwrite: bool = False,
    create_parent_dirs: bool = True,
) -> str:
    """将文本写入允许目录内的文件，并以 JSON 返回写入结果。

    Args:
        file_path: 目标文件路径。相对路径以服务进程的当前工作目录为基准。
        content: 要写入的文本内容。
        encoding: utf-8、utf-8-sig 或 gb18030，默认 utf-8。
        overwrite: 文件已存在时是否覆盖，默认 false。
        create_parent_dirs: 父目录不存在时是否自动创建，默认 true。
    """
    from agent_platform.config.settings import settings

    try:
        if encoding not in SUPPORTED_ENCODINGS:
            raise ValueError(
                f"不支持编码 '{encoding}'，可用值: {', '.join(SUPPORTED_ENCODINGS)}"
            )
        if "\x00" in content:
            raise ValueError("content 包含 NUL 字符，不能作为文本写入")

        path = _resolve_allowed_path(
            file_path,
            settings.file_write_allowed_roots,
            "写入",
        )
        if path.suffix.lower() not in TEXT_SUFFIXES:
            supported = ", ".join(sorted(TEXT_SUFFIXES))
            raise ValueError(f"不支持的文件类型 '{path.suffix}'。支持: {supported}")
        if path.exists():
            if not path.is_file():
                raise ValueError(f"路径不是文件: {file_path}")
            if not overwrite:
                raise FileExistsError(f"文件已存在，如需覆盖请设置 overwrite=true: {file_path}")

        payload = content.encode(encoding)
        if len(payload) > settings.file_write_max_bytes:
            raise ValueError(
                f"写入内容过大: {len(payload)} bytes，最大允许 "
                f"{settings.file_write_max_bytes} bytes"
            )

        if not path.parent.exists():
            if not create_parent_dirs:
                raise FileNotFoundError(f"父目录不存在: {path.parent}")
            path.parent.mkdir(parents=True, exist_ok=True)

        existed = path.exists()
        path.write_bytes(payload)
        return _result(
            success=True,
            path=str(path),
            encoding=encoding,
            chars_written=len(content),
            bytes_written=len(payload),
            overwritten=existed,
        )
    except Exception as exc:
        return _result(
            success=False,
            error=f"{type(exc).__name__}: {exc}",
            file_path=file_path,
        )


def register_file_tools() -> None:
    from agent_platform.tools.registry import register

    register(read_file)
    register(write_file)
