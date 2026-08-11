"""Detect the agentcad executable / Python environment on this machine.

Prints a JSON line with:
- `agentcad`: path to the agentcad CLI executable
- `agentcad_python`: a Python that can import agentcad (used to run make_viewer.py)

Strategy: find the agentcad CLI first (via PATH or known conda locations), then
derive the sibling Python in the same env from the CLI's location. This avoids
hardcoding machine-specific paths, so the repo is portable.

Usage:
    python find_agentcad.py
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path


def _env_dir_from_cli(cli: str) -> Path | None:
    """Given an agentcad CLI path, return its conda env dir.

    - Windows: <env>/Scripts/agentcad.exe -> <env>
    - Linux:   <env>/bin/agentcad         -> <env>
    """
    p = Path(cli)
    # up from the bin dir
    if len(p.parents) >= 2:
        parent = p.parents[0]  # Scripts or bin
        if parent.name in ("Scripts", "bin"):
            return p.parents[1]
    return None


def _sibling_python(cli: str) -> Path | None:
    """Find the python interpreter in the same env as the agentcad CLI."""
    env_dir = _env_dir_from_cli(cli)
    if env_dir is None:
        return None
    for cand in (
        env_dir / "Scripts" / "python.exe",
        env_dir / "python.exe",
        env_dir / "bin" / "python",
    ):
        if cand.exists():
            return cand
    return None


def main() -> None:
    result: dict = {"agentcad": "", "agentcad_python": "", "hints": []}

    # 1. Locate the agentcad CLI
    cli = shutil.which("agentcad")
    if cli:
        # 统一正斜杠，bash 工具用 shlex 解析，反斜杠会被当转义符吞掉
        result["agentcad"] = Path(cli).as_posix()
    else:
        # Windows/macOS/Linux known conda layouts (repo-agnostic)
        for p in (
            Path(sys.prefix).parent / "Scripts" / "agentcad.exe",
            Path(sys.prefix).parent / "Scripts" / "agentcad",
            Path(sys.prefix).parent / "bin" / "agentcad",
            Path.home() / "anaconda3" / "envs" / "agentcad-py312" / "Scripts" / "agentcad.exe",
            Path.home() / "anaconda3" / "envs" / "agentcad-py312" / "bin" / "agentcad",
            Path.home() / "miniconda3" / "envs" / "agentcad-py312" / "Scripts" / "agentcad.exe",
            Path.home() / "miniconda3" / "envs" / "agentcad-py312" / "bin" / "agentcad",
            Path("D:/software/anaconda/anaconda/envs/agentcad-py312/Scripts/agentcad.exe"),
            Path("/opt/anaconda3/envs/agentcad-py312/bin/agentcad"),
        ):
            if p.exists():
                result["agentcad"] = p.as_posix()
                break

    # 2. Derive the sibling python from the CLI location (fast, no subprocess)
    if result["agentcad"]:
        sp = _sibling_python(result["agentcad"])
        if sp and sp.exists():
            result["agentcad_python"] = sp.as_posix()
        else:
            # fallback: current interpreter
            result["agentcad_python"] = Path(sys.executable).as_posix()

    if not result["agentcad"]:
        result["hints"].append(
            "未找到 agentcad。运行 setup_agentcad.ps1 (Windows) 或 setup_agentcad.sh (Linux) 自动安装。"
        )
    elif not result["agentcad_python"]:
        result["hints"].append("找到 agentcad 但无法定位其 Python 环境。")

    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
