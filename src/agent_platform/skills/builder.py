"""声明式 Skill → LangGraph ReAct Agent 构建器。

从一个 DeclarativeSkill 对象 + 工具列表动态构建可执行的 Agent。
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from typing import TYPE_CHECKING

from langchain.agents import create_agent
from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool

from agent_platform.skills.registry import DeclarativeSkill

if TYPE_CHECKING:
    from langgraph.graph.state import CompiledStateGraph

logger = logging.getLogger(__name__)

COMPLETE_INSTRUCTION = """
## 结束任务

当你完成任务后，**必须**调用 `{complete_tool}` 工具来提交结果。
不要在调用 {complete_tool} 之外输出最终结论。
"""

TOOL_USAGE_INSTRUCTION = """
## 运行时工具

以下工具已绑定到当前 Agent：
{tools}

- 根据任务需要和工具说明选择工具，不要调用与当前任务无关的工具。
- 涉及外部资源、环境状态或产生实际操作时，应通过适用工具获取或执行，
  不要把未经验证的假设当作执行结果。
- 工具返回失败时，应依据错误信息调整操作或向用户准确说明，不能声称操作已成功。
- Skill 明确引用自身目录中的脚本、参考资料或资源时，应优先复用这些现有内容。
{source_location}
"""


def build_skill_agent(
    model: BaseChatModel,
    skill: DeclarativeSkill,
    tools: list[BaseTool],
    *,
    max_tool_calls: int = 10,
    session_id: str = "",
    model_identity: str = "",
) -> "CompiledStateGraph":
    """从 Skill 定义动态构建一个 LangGraph ReAct Agent。"""
    from agent_platform.skills.complete import get_complete_tool

    complete_tool = get_complete_tool(skill.complete_tool)
    if complete_tool is None:
        raise RuntimeError(
            f"Skill '{skill.name}' 的结束工具未注册: {skill.complete_tool}"
        )

    bound_tool_names = [tool.name for tool in tools]
    missing_tools = [name for name in skill.tools if name not in bound_tool_names]
    if missing_tools:
        raise RuntimeError(
            f"Skill '{skill.name}' 声明的工具没有绑定到 Agent: "
            f"{', '.join(missing_tools)}；实际绑定: "
            f"{', '.join(bound_tool_names) or '无'}"
        )

    all_tools = list(tools) + [complete_tool]
    prompt = _build_prompt(
        skill,
        max_tool_calls,
        model_identity=model_identity,
        bound_tool_names=bound_tool_names,
    )

    return create_agent(model, all_tools, system_prompt=prompt)


def resolve_skill_tools(
    skill: DeclarativeSkill,
    registered_tools: Mapping[str, BaseTool],
) -> list[BaseTool]:
    """解析并校验 Skill 声明的业务工具和结束工具。"""
    from agent_platform.skills.complete import get_complete_tool

    missing_tools = [name for name in skill.tools if name not in registered_tools]
    if missing_tools:
        raise RuntimeError(f"Skill '{skill.name}' 的工具未注册: {', '.join(missing_tools)}")
    if get_complete_tool(skill.complete_tool) is None:
        raise RuntimeError(
            f"Skill '{skill.name}' 配置的 complete_tool 不存在: {skill.complete_tool}"
        )
    return [registered_tools[name] for name in skill.tools]


def recursion_limit_for_tool_calls(max_tool_calls: int) -> int:
    """Return enough LangGraph supersteps for the configured tool-call budget.

    A ReAct cycle normally consumes one agent step and one tool step.  Keep a
    few extra steps for the initial model call and the final complete tool.
    """
    return max(25, max_tool_calls * 2 + 5)


def _build_prompt(
    skill: DeclarativeSkill,
    max_tool_calls: int,
    *,
    model_identity: str = "",
    bound_tool_names: list[str] | None = None,
) -> str:
    body = skill.body
    if "{max_tool_calls}" in body:
        body = body.replace("{max_tool_calls}", str(max_tool_calls))

    effective_tool_names = skill.tools if bound_tool_names is None else bound_tool_names
    tools = ", ".join(f"`{name}`" for name in effective_tool_names) or "（无）"
    source_location = (
        f"- 当前 Skill 目录：`{skill.source_dir}`。Skill 中引用的相对路径应以此目录或项目根目录解析。"
        if skill.source_dir
        else ""
    )
    parts = [
        TOOL_USAGE_INSTRUCTION.format(
            tools=tools,
            source_location=source_location,
        ),
        body,
    ]

    if model_identity:
        parts.append(f"\n## 运行时模型身份\n\n{model_identity}")

    refs = skill.load_all_references()
    if refs:
        parts.append("\n## 参考资料\n")
        for name, content in refs.items():
            parts.append(f"### {name}\n```\n{content}\n```\n")

    parts.append(COMPLETE_INSTRUCTION.format(complete_tool=skill.complete_tool))

    return "\n".join(parts)


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
