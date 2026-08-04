"""本地开发启动脚本。

在启动 uvicorn 前把 agentcad 的可执行目录加入 PATH，这样中台的
bash 工具（LLM 调用 agentcad 生成 CAD）能解析到 agentcad 命令。

用法:
    python start_dev.py            # 默认 0.0.0.0:8000
    python start_dev.py --port 9000

说明:
- 通过环境变量 AGENTCAD_DIR 覆盖 agentcad 目录，默认用 conda 的
  agentcad-py312 环境。
- 需要 PYTHONPATH=src 让 uvicorn 找到 agent_platform 包（源码路径
  含中文时 .pth 文件会失效，见 docs/agentcad-部署说明.md）。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# 默认 agentcad 可执行目录（Windows conda 路径）
DEFAULT_AGENTCAD_DIR = r"D:\software\anaconda\anaconda\envs\agentcad-py312\Scripts"


def _prepend_to_path(directory: str) -> None:
    """把目录加入 PATH 前缀，确保 shutil.which 能解析到其中的可执行文件。"""
    if not directory or not Path(directory).exists():
        print(f"[warn] agentcad 目录不存在，跳过: {directory}")
        return
    sep = os.pathsep
    existing = os.environ.get("PATH", "")
    os.environ["PATH"] = directory + sep + existing
    print(f"[ok] agentcad 目录已加入 PATH: {directory}")


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="本地启动智能体中台")
    parser.add_argument("--port", type=int, default=8000, help="监听端口")
    parser.add_argument("--host", default="0.0.0.0", help="监听地址")
    args = parser.parse_args()

    # 0. 强制 UTF-8，避免中文 Windows 上 GBK 编码导致 agentcad 写
    #    viewer.html 崩溃。agentcad 作为 bash 工具的子进程会继承此设置。
    os.environ["PYTHONUTF8"] = "1"

    # 1. 注入 agentcad 路径
    agentcad_dir = os.environ.get("AGENTCAD_DIR", DEFAULT_AGENTCAD_DIR)
    _prepend_to_path(agentcad_dir)

    # 2. 确保项目根目录的 src 在 Python 路径中
    root = Path(__file__).resolve().parent
    src_dir = str(root / "src")
    if src_dir not in sys.path:
        sys.path.insert(0, src_dir)
    os.environ["PYTHONPATH"] = src_dir + os.pathsep + os.environ.get("PYTHONPATH", "")

    # 3. 启动 uvicorn
    import uvicorn

    print(f"[ok] 启动后端: http://{args.host}:{args.port}")
    uvicorn.run("agent_platform.api.app:app", host=args.host, port=args.port)


if __name__ == "__main__":
    raise SystemExit(main())
