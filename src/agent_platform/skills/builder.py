"""声明式 Skill → LangGraph ReAct Agent 构建器。

从一个 DeclarativeSkill 对象 + 工具列表动态构建可执行的 Agent。
"""

from __future__ import annotations

import functools
import hashlib
import json
import logging
from typing import TYPE_CHECKING

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import ToolMessage
from langchain_core.tools import BaseTool
from langgraph.prebuilt import ToolNode, create_react_agent

from agent_platform.skills.registry import DeclarativeSkill

if TYPE_CHECKING:
    from langgraph.graph.state import CompiledStateGraph

logger = logging.getLogger(__name__)

COMPLETE_INSTRUCTION = """
## 结束任务

当你完成任务后，**必须**调用 `{complete_tool}` 工具来提交结果。
不要在调用 {complete_tool} 之外输出最终结论。
"""


def build_skill_agent(
    model: BaseChatModel,
    skill: DeclarativeSkill,
    tools: list[BaseTool],
    *,
    max_tool_calls: int = 10,
    session_id: str = "",
) -> "CompiledStateGraph":
    """从 Skill 定义动态构建一个 LangGraph ReAct Agent。"""
    from agent_platform.skills.complete import get_complete_tool

    complete_tool = get_complete_tool(skill.complete_tool)
    if complete_tool is None:
        raise ValueError(f"Complete tool '{skill.complete_tool}' not registered for skill '{skill.name}'")

    all_tools = list(tools) + [complete_tool]
    prompt = _build_prompt(skill, max_tool_calls)

    wrap_fn = _make_tool_counter(max_tool_calls)
    tool_node = ToolNode(all_tools, wrap_tool_call=wrap_fn)

    return create_react_agent(model, tool_node, prompt=prompt)


def _build_prompt(skill: DeclarativeSkill, max_tool_calls: int) -> str:
    body = skill.body
    if "{max_tool_calls}" in body:
        body = body.replace("{max_tool_calls}", str(max_tool_calls))

    parts = [body]

    refs = skill.load_all_references()
    if refs:
        parts.append("\n## 参考资料\n")
        for name, content in refs.items():
            parts.append(f"### {name}\n```\n{content}\n```\n")

    parts.append(
        COMPLETE_INSTRUCTION.format(complete_tool=skill.complete_tool)
    )

    return "\n".join(parts)


def _make_tool_counter(max_calls: int):
    """包装工具调用：超过次数上限或重复调用时拦截。"""
    call_history: list[str] = []

    def wrap_tool_call(request, execute):
        call = request.tool_call
        tool_name = call["name"]

        # complete 工具不受次数限制
        if tool_name.startswith("complete"):
            return execute(request)

        fingerprint = _fingerprint(tool_name, call.get("args", {}))

        if len(call_history) >= max_calls:
            return ToolMessage(
                content=f"[系统提示：工具调用次数已达上限({max_calls})，请立即调用 {skill.complete_tool} 提交结果]",
                tool_call_id=call["id"],
                name=tool_name,
            )

        if fingerprint in call_history[-3:]:
            return ToolMessage(
                content="[系统提示：重复调用已被阻止，请基于已有信息调用 complete 工具提交结果]",
                tool_call_id=call["id"],
                name=tool_name,
            )

        result = execute(request)
        call_history.append(fingerprint)
        return result

    return wrap_tool_call


def _fingerprint(tool_name: str, args: dict) -> str:
    raw = tool_name + json.dumps(args, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def extract_complete_result(messages: list) -> dict:
    """从 Agent 执行结果的消息列表中提取 complete_xxx 调用的结构化参数。"""
    from langchain_core.messages import AIMessage, ToolMessage

    # 优先从 AIMessage 中找 tool_calls
    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and msg.tool_calls:
            for tc in msg.tool_calls:
                if tc["name"].startswith("complete"):
                    return dict(tc["args"])

    # 回退：从 ToolMessage 中解析
    for msg in reversed(messages):
        if isinstance(msg, ToolMessage) and getattr(msg, "name", "").startswith("complete"):
            try:
                data = json.loads(msg.content)
                if isinstance(data, dict) and "summary" in data:
                    return data
            except (json.JSONDecodeError, TypeError):
                continue

    # 最终回退：最后一条消息的 content
    for msg in reversed(messages):
        if hasattr(msg, "content") and msg.content:
            content = msg.content
            if len(content) > 300:
                return {"summary": content[:200] + "...", "detail": content}
            return {"summary": content, "detail": content}

    return {"summary": "", "detail": ""}
