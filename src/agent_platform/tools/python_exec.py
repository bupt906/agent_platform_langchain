"""沙箱化 Python 执行器。

提供 execute_python 工具，让 LLM Agent 在受限环境中执行 Python 代码。
"""

from __future__ import annotations

import builtins
import io
import json
import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from contextlib import redirect_stdout

from langchain_core.tools import tool

logger = logging.getLogger(__name__)

# ── 安全白名单 ──────────────────────────────────────────────

SAFE_BUILTIN_NAMES = {
    "print", "len", "range", "int", "float", "str", "bool", "list", "dict",
    "tuple", "set", "abs", "max", "min", "sum", "sorted", "enumerate",
    "zip", "map", "filter", "any", "all", "isinstance", "hasattr", "getattr",
    "type", "round", "repr", "ascii", "format", "bytes", "bytearray",
    "ord", "chr", "reversed", "iter", "next", "slice",
    "frozenset", "property", "staticmethod", "classmethod", "object", "super",
    "Exception", "ValueError", "TypeError", "KeyError", "IndexError",
    "StopIteration", "ZeroDivisionError", "AttributeError", "ImportError",
    "True", "False", "None",
}

_SAFE_BUILTINS = {k: getattr(builtins, k) for k in SAFE_BUILTIN_NAMES if hasattr(builtins, k)}

_ALLOWED_IMPORTS = {
    "json", "math", "datetime", "random", "collections", "itertools",
    "functools", "typing", "re", "decimal",
    "plotly", "plotly.graph_objects", "plotly.io", "plotly.express",
    "pandas", "numpy",
    "openpyxl", "python-docx",
    "markdown",
    "requests",
}

_ORIGINAL_IMPORT = builtins.__import__

PYTHON_EXEC_TIMEOUT = 30


def _safe_import(name, *args, **kwargs):
    if name in _ALLOWED_IMPORTS or any(name.startswith(p + ".") for p in _ALLOWED_IMPORTS):
        return _ORIGINAL_IMPORT(name, *args, **kwargs)
    raise ImportError(f"模块 '{name}' 不在沙箱白名单中。可用模块: {sorted(_ALLOWED_IMPORTS)}")


def _get_safe_globals() -> dict:
    safe = dict(_SAFE_BUILTINS)
    safe["__import__"] = _safe_import
    g = {"__builtins__": safe}
    for mod_name in ("json", "math", "datetime", "random", "collections", "itertools", "functools"):
        try:
            g[mod_name] = _ORIGINAL_IMPORT(mod_name)
        except ImportError:
            pass
    return g


# ── 工具 ────────────────────────────────────────────────────

@tool
def execute_python(code: str, session_id: str = "") -> str:
    """执行 Python 代码并返回输出。

    沙箱环境：受限内置函数 + 导入白名单 + 30 秒超时。
    如果通过 load_data 加载了数据，相应的 DataFrame 变量会自动在沙箱中可用。
    """
    output_buf = io.StringIO()
    ns = _get_safe_globals()

    # 注入 session 隔离变量
    if session_id:
        try:
            from agent_platform.tools.data_tools import get_session_vars
            svars = get_session_vars(session_id)
            if svars:
                ns.update(svars)
                ns["pd"] = _ORIGINAL_IMPORT("pandas")
                ns["np"] = _ORIGINAL_IMPORT("numpy")
        except Exception:
            pass

    safe_keys = set(ns.keys())

    def _run():
        with redirect_stdout(output_buf):
            compiled = compile(code, "<sandbox>", "exec")
            exec(compiled, ns)

    pool = ThreadPoolExecutor(max_workers=1)
    future = pool.submit(_run)
    try:
        future.result(timeout=PYTHON_EXEC_TIMEOUT)
    except FuturesTimeoutError:
        pool.shutdown(wait=False)
        return json.dumps({
            "error": f"TimeoutError: 代码执行超过 {PYTHON_EXEC_TIMEOUT} 秒，已终止",
            "stdout": output_buf.getvalue()[:10000],
            "success": False,
        }, ensure_ascii=False)
    except Exception as e:
        pool.shutdown(wait=False)
        import traceback
        tb = traceback.format_exc()
        return json.dumps({
            "error": f"{type(e).__name__}: {e}",
            "traceback": tb[-1000:],
            "stdout": output_buf.getvalue()[:10000],
            "success": False,
        }, ensure_ascii=False)

    pool.shutdown(wait=False)

    stdout = output_buf.getvalue()
    result_vars = {
        k: repr(v) for k, v in ns.items()
        if k not in safe_keys and not k.startswith("_") and not callable(v)
    }

    return json.dumps({
        "stdout": stdout[:50000],
        "variables": result_vars,
        "success": True,
    }, ensure_ascii=False, default=str)


def register_python_tool():
    from agent_platform.tools.registry import register
    register(execute_python)
