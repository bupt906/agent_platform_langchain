"""Generate a measured 3D viewer for a STEP file WITHOUT opening a browser.

Wraps agentcad's internal renderer so the viewer.html is written to disk but
no browser window pops up. The agentcad `view --measure` command always opens
the browser, which is unwanted inside the platform.

Usage:
    python make_viewer.py <file.step> [--measure] [--out <path>]

Outputs a JSON line on stdout: {"viewer": "<relative path>"} on success.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Render a STEP file to a measured viewer HTML")
    parser.add_argument("file", help="Path to STEP/STP/BREP file")
    parser.add_argument("--measure", action="store_true", help="Embed measurement review data")
    parser.add_argument("--out", default="", help="Output viewer.html path (default: next to the input)")
    args = parser.parse_args()

    file_path = Path(args.file)
    if not file_path.exists():
        print(json.dumps({"error": f"File not found: {args.file}"}))
        return 1

    try:
        from agentcad.commands.view import (
            _build_review_payload,
            _render_single,
            _resolve_to_glb,
        )
    except ImportError as exc:
        print(json.dumps({"error": f"agentcad import failed: {exc}"}))
        return 1

    # 构造测量数据（可选）
    review, err = _build_review_payload(str(file_path), include_measure=args.measure)
    if err:
        print(json.dumps({"error": f"measure failed: {err}"}))
        return 1

    # 解析为 GLB，渲染 viewer 文件（不打开浏览器）
    glb, err = _resolve_to_glb(str(file_path))
    if err:
        print(json.dumps({"error": f"resolve GLB failed: {err}"}))
        return 1

    html_path, _url = _render_single(glb, review=review)

    # 如果指定了 --out，把 viewer 复制/移动到目标位置
    final_path = html_path
    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        html_path.rename(out_path)
        final_path = out_path

    print(json.dumps({"viewer": str(final_path), "status": "success"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
