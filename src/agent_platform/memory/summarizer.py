"""对话摘要器。

当对话轮次超过阈值时，调用 LLM 自动生成摘要，压缩上下文。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent_platform.models.provider import ModelProvider

logger = logging.getLogger(__name__)

_SUMMARIZE_PROMPT = """请将以下对话历史压缩为一段简洁的摘要（不超过 200 字）。
保留关键事实、用户偏好和重要决策。摘要将替代原始对话注入后续的上下文。

对话历史：
{history}

摘要："""


class ConversationSummarizer:
    """使用 LLM 对对话历史进行自动摘要压缩。"""

    def __init__(self, model_provider: ModelProvider) -> None:
        self._model_provider = model_provider

    async def summarize(self, history: list[dict], model_id: str | None = None) -> str:
        """将对话历史列表压缩为一段摘要文本。

        Args:
            history: [{"role": "user"|"assistant", "content": "..."}, ...]
            model_id: 可选，指定用于摘要的模型；省略则使用默认模型

        Returns:
            摘要字符串
        """
        if not history:
            return ""

        # 格式化对话历史
        lines = []
        for msg in history[-20:]:  # 最多取最近 20 条
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            if content:
                lines.append(f"[{role}]: {content[:500]}")  # 每条消息截断至 500 字符

        history_text = "\n".join(lines)
        prompt = _SUMMARIZE_PROMPT.format(history=history_text)

        from langchain_core.messages import HumanMessage

        model = self._model_provider.get_model(model_id)
        result = await model.ainvoke([HumanMessage(content=prompt)])
        return result.content.strip()

    async def maybe_summarize(
        self,
        session_id: str,
        turn_count: int,
        threshold: int = 10,
    ) -> bool:
        """检查是否触发摘要阈值。

        Returns:
            True 如果达到了阈值（调用方应随后调用 summarize()）
        """
        return turn_count >= threshold
