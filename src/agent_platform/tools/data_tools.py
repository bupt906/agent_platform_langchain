"""数据加载与 Session 隔离工具。

让 declarative skill 的 Agent 在 execute_python 之前加载结构化数据。
"""

from __future__ import annotations

import logging

from langchain_core.tools import tool

logger = logging.getLogger(__name__)

_session_vars: dict[str, dict] = {}


def get_session_vars(session_id: str) -> dict:
    return _session_vars.get(session_id, {})


def clear_session_vars(session_id: str) -> None:
    _session_vars.pop(session_id, None)


@tool
def load_data(data_keys: str, session_id: str = "") -> str:
    """加载缓存数据供后续 execute_python 使用。

    data_keys 为逗号分隔的 key 列表，如 "sql_abc,sql_def"。
    第一个加载为 data，后续为 data_2、data_3 等。
    """
    if not session_id:
        return "错误: session_id 为空，无法加载数据。"

    keys = [k.strip() for k in data_keys.split(",") if k.strip()]
    if not keys:
        return "错误: 未指定 data_keys。"

    from agent_platform.tools.data_store import load_dataframe

    _session_vars.setdefault(session_id, {})

    results = []
    for i, key in enumerate(keys):
        var_name = "data" if i == 0 else f"data_{i + 1}"
        try:
            df = load_dataframe(session_id, key)
            _session_vars[session_id][var_name] = df
            cols = list(df.columns) if hasattr(df, "columns") else list(df[0].keys()) if isinstance(df, list) else []
            info = f"{var_name}: {len(df)} 行 × {len(cols)} 列"
            if cols:
                info += f" ({', '.join(str(c) for c in cols[:10])})"
            results.append(info)
            logger.info("load_data: %s → %s (%d rows)", key, var_name, len(df))
        except KeyError:
            results.append(f"{var_name}: [{key}] 数据不存在，请检查可用数据列表获取正确的 data_key")
        except Exception as e:
            results.append(f"{var_name}: [{key}] 加载失败: {e}")

    return "\n".join(results)


def register_data_tools():
    from agent_platform.tools.registry import register
    register(load_data)
