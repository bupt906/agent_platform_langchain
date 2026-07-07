"""工具调用预算管理。

按 session_id 追踪工具调用次数，超出预算后阻止进一步的工具调用。
"""

from __future__ import annotations

import logging
from collections import defaultdict

logger = logging.getLogger(__name__)


class ToolBudgetManager:
    """按 session 追踪工具调用预算。"""

    def __init__(self, max_calls_per_session: int = 50) -> None:
        self._max_calls = max_calls_per_session
        self._call_counts: dict[str, int] = defaultdict(int)

    def can_call(self, session_id: str) -> bool:
        """检查指定 session 是否还有剩余调用配额。"""
        return self._call_counts.get(session_id, 0) < self._max_calls

    def record_call(self, session_id: str, tool_name: str = "") -> None:
        """记录一次工具调用。"""
        self._call_counts[session_id] += 1
        remaining = self._max_calls - self._call_counts[session_id]
        if remaining <= 5:
            logger.info("会话 %s 工具调用配额即将耗尽: 剩余 %d 次", session_id[:8], max(0, remaining))

    def remaining(self, session_id: str) -> int:
        """返回剩余调用次数。"""
        return max(0, self._max_calls - self._call_counts.get(session_id, 0))

    def reset(self, session_id: str) -> None:
        """重置指定 session 的调用计数。"""
        self._call_counts.pop(session_id, None)

    def get_usage(self, session_id: str) -> dict:
        """获取当前 session 的工具调用使用情况。"""
        used = self._call_counts.get(session_id, 0)
        return {
            "session_id": session_id,
            "calls_used": used,
            "calls_limit": self._max_calls,
            "calls_remaining": max(0, self._max_calls - used),
        }
