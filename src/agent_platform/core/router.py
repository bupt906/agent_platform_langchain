from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Literal

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from agent_platform.graph.orchestration import OrchestrationEngine
from agent_platform.graph.patterns import ExecutionPlan, SubTask

if TYPE_CHECKING:
    from agent_platform.core.deps import PlatformDeps

logger = logging.getLogger(__name__)


class RouterDecision(BaseModel):
    """路由决策结果。"""

    skill_name: str
    rewritten_query: str
    confidence: float = Field(ge=0.0, le=1.0)
    mode: Literal["single", "multi"] = "single"
    execution_plan: ExecutionPlan | None = None


def _extract_tokens_from_message(msg) -> dict[str, int]:
    """从单个 AIMessage 中提取 token 用量。"""
    tokens = {"prompt": 0, "completion": 0, "total": 0}
    try:
        um = getattr(msg, "usage_metadata", None) or {}
        if um.get("total_tokens"):
            tokens["prompt"] = um.get("input_tokens", 0)
            tokens["completion"] = um.get("output_tokens", 0)
            tokens["total"] = um.get("total_tokens", 0)
            return tokens
        meta = getattr(msg, "response_metadata", {}) or {}
        usage = meta.get("token_usage", {})
        if usage:
            tokens["prompt"] = usage.get("prompt_tokens", 0)
            tokens["completion"] = usage.get("completion_tokens", 0)
            tokens["total"] = usage.get("total_tokens", 0)
    except Exception:
        pass
    return tokens


def _extract_tokens(result: dict | None) -> dict[str, int]:
    """从 agent.ainvoke 返回的 state dict 中提取 token 用量。

    遍历 messages 列表，从最后一个 AIMessage 提取。
    如果是 input 是 dict 没有 messages 字段，直接返回 0。
    """
    if result is None:
        return {"prompt": 0, "completion": 0, "total": 0}
    try:
        messages = result.get("messages", [])
        for msg in reversed(messages):
            t = _extract_tokens_from_message(msg)
            if t["total"] > 0:
                return t
    except Exception:
        pass
    return {"prompt": 0, "completion": 0, "total": 0}


def _build_router_prompt(deps: PlatformDeps) -> str:
    # 优先使用分层 builder，回退到原有拼接逻辑
    if deps.prompt_builder:
        return deps.prompt_builder.build_router_prompt(deps.skill_registry)

    skills = deps.skill_registry.list_skills()
    skill_descriptions = []
    for s in skills:
        dep_info = f"  依赖技能: {', '.join(s.dependencies)}" if s.dependencies else ""
        examples = "\n".join(f"    - {e}" for e in s.examples)
        skill_descriptions.append(
            f"- **{s.name}**: {s.description}\n"
            f"  示例问题:\n{examples}\n{dep_info}"
        )
    skills_text = "\n".join(skill_descriptions)

    return f"""\
你是一个智能路由器，负责分析用户意图并选择最合适的处理方式。

## 可用技能
{skills_text}

## 路由规则
1. 如果用户问题可以由单一技能处理，选择 mode="single"，填写对应 skill_name
2. 如果需要多个技能协同，选择 mode="multi"，skill_name 填 "multi_agent"，
   并提供 execution_plan：
   - mode: "sequential"（顺序执行）/ "parallel"（并行执行）/ "orchestrator"（动态编排）
   - subtasks: 子任务列表，每个包含 id、skill_name、description
3. 如果没有合适的技能匹配，skill_name 填 "general"，mode="single"
4. rewritten_query 是对用户原始问题的优化改写，使其更适合目标技能处理
5. confidence 是你对路由决策的置信度 (0.0-1.0)

请以 JSON 格式输出路由决策。"""


async def resolve_route(
    message: str,
    deps: PlatformDeps,
    *,
    model_id: str | None = None,
) -> RouterDecision:
    """分析用户意图，返回路由决策。chat 端点的共享入口。"""
    model = deps.model_provider.get_model(model_id)
    # method="json_mode" 兼容 DeepSeek（不支持 json_schema 但支持 json_object）
    structured_model = model.with_structured_output(RouterDecision, method="json_mode")
    system_prompt = _build_router_prompt(deps)
    decision: RouterDecision = await structured_model.ainvoke(
        [SystemMessage(content=system_prompt), HumanMessage(content=message)]
    )

    logger.info(
        "路由决策: skill=%s, mode=%s, confidence=%.2f",
        decision.skill_name,
        decision.mode,
        decision.confidence,
    )
    return decision


async def execute_decision(
    decision: RouterDecision,
    message: str,
    deps: PlatformDeps,
    *,
    model_id: str | None = None,
    session_id: str | None = None,
) -> str:
    """执行路由决策，返回最终回复文本。"""
    invoke_cfg = _build_invoke_config(session_id)
    start_time = time.monotonic()
    reply = ""
    error = None
    tokens = {"prompt": 0, "completion": 0, "total": 0}

    try:
        if decision.mode == "multi" and decision.execution_plan:
            engine = OrchestrationEngine(deps)
            reply = await engine.execute(message, decision.execution_plan)
        else:
            skill = deps.skill_registry.get(decision.skill_name)
            if skill:
                skills = deps.skill_registry.get_all_skills()
                agent = skill.compose(skills, deps.model_provider) or skill.create_agent(
                    deps.model_provider, checkpointer=deps.checkpointer
                )
                agent_result = await agent.ainvoke(
                    {"messages": [HumanMessage(content=decision.rewritten_query)]},
                    config=invoke_cfg,
                )
                reply = agent_result["messages"][-1].content
                tokens = _extract_tokens(agent_result)
            else:
                # 检查声明式 Skill 匹配
                declarative = deps.declarative_registry.get(decision.skill_name) if deps.declarative_registry else None
                if declarative and deps.declarative_registry:
                    reply, tokens = await _execute_declarative_skill(
                        declarative, message, deps, model_id, invoke_cfg
                    )
                    decision.skill_name = f"skill:{declarative.name}"
                else:
                    reply, tokens = await _general_response(
                        message, deps, model_id, invoke_cfg
                    )
    except Exception as e:
        error = str(e)
        logger.error("决策执行失败: %s", error, exc_info=True)
        reply = f"抱歉，处理请求时出现错误: {error}"

    # ── 持久化对话记录 ──
    if deps.session_store and session_id:
        try:
            await deps.session_store.add_turn(
                session_id=session_id,
                user_message=message,
                assistant_message=reply,
                skill_used=decision.skill_name,
                tokens_used=0,
                duration_ms=(time.monotonic() - start_time) * 1000,
            )
        except Exception:
            logger.warning("持久化对话记录失败", exc_info=True)

    # ── 审计日志 ──
    if deps.audit_store:
        try:
            from agent_platform.audit.schema import AuditRecord

            await deps.audit_store.record(
                AuditRecord(
                    session_id=session_id,
                    agent_type=f"skill:{decision.skill_name}" if decision.skill_name not in ("general", "multi_agent") else decision.skill_name,
                    user_message=message,
                    assistant_message=reply,
                    tokens_prompt=tokens["prompt"],
                    tokens_completion=tokens["completion"],
                    tokens_total=tokens["total"],
                    duration_ms=(time.monotonic() - start_time) * 1000,
                    skill_used=decision.skill_name,
                    router_confidence=decision.confidence,
                    error=error,
                )
            )
        except Exception:
            logger.warning("审计日志记录失败", exc_info=True)

    return reply


async def execute_skill_direct(
    skill_name: str,
    message: str,
    deps: PlatformDeps,
    *,
    model_id: str | None = None,
    session_id: str | None = None,
) -> str:
    """跳过路由，直接调用指定技能（Python Agent 或声明式 Skill）。"""
    invoke_cfg = _build_invoke_config(session_id)

    # 先查 Python Agent，再查声明式 Skill
    skill = deps.skill_registry.get(skill_name)
    declarative = None
    if not skill and deps.declarative_registry:
        declarative = deps.declarative_registry.get(skill_name)

    if not skill and not declarative:
        return f"未找到技能: {skill_name}"

    # 命中声明式 Skill：走动态构建路径
    if declarative:
        reply, tokens = await _execute_declarative_skill(
            declarative, message, deps, model_id, invoke_cfg
        )
        # 记录 session 和审计
        return reply

    start_time = time.monotonic()
    reply = ""
    error = None
    tokens = {"prompt": 0, "completion": 0, "total": 0}

    try:
        skills = deps.skill_registry.get_all_skills()
        agent = skill.compose(skills, deps.model_provider) or skill.create_agent(
            deps.model_provider, checkpointer=deps.checkpointer
        )
        result = await agent.ainvoke(
            {"messages": [HumanMessage(content=message)]},
            config=invoke_cfg,
        )
        reply = result["messages"][-1].content
        tokens = _extract_tokens(result)
    except Exception as e:
        error = str(e)
        logger.error("技能直接调用失败: %s", error, exc_info=True)
        reply = f"抱歉，处理请求时出现错误: {error}"

    duration_ms = (time.monotonic() - start_time) * 1000

    # ── 持久化对话记录 ──
    if deps.session_store and session_id:
        try:
            await deps.session_store.add_turn(
                session_id=session_id,
                user_message=message,
                assistant_message=reply,
                skill_used=skill_name,
                duration_ms=duration_ms,
            )
        except Exception:
            logger.warning("持久化对话记录失败", exc_info=True)

    # ── 审计日志 ──
    if deps.audit_store:
        try:
            from agent_platform.audit.schema import AuditRecord

            await deps.audit_store.record(
                AuditRecord(
                    session_id=session_id,
                    agent_type=f"skill:{skill_name}",
                    user_message=message,
                    assistant_message=reply,
                    tokens_prompt=tokens["prompt"],
                    tokens_completion=tokens["completion"],
                    tokens_total=tokens["total"],
                    duration_ms=duration_ms,
                    skill_used=skill_name,
                    error=error,
                )
            )
        except Exception:
            logger.warning("审计日志记录失败", exc_info=True)

    return reply


def _build_invoke_config(session_id: str | None) -> dict:
    """构建 LangGraph ainvoke 的 config dict。"""
    if session_id:
        return {"configurable": {"thread_id": session_id}}
    # SqliteSaver 等持久化 checkpointer 要求必须有 thread_id
    from uuid import uuid4

    return {"configurable": {"thread_id": uuid4().hex}}


async def _execute_declarative_skill(
    skill, message: str, deps: PlatformDeps, model_id: str | None, invoke_cfg: dict
) -> tuple[str, dict]:
    """执行声明式 Skill。"""
    from agent_platform.skills.builder import (
        build_skill_agent,
        extract_complete_result,
        recursion_limit_for_tool_calls,
    )
    from agent_platform.tools.registry import tool_map

    model = deps.model_provider.get_model(model_id)
    from agent_platform.config.settings import settings as _settings
    max_calls = _settings.declarative_skills_max_tool_calls

    tools = []
    for tool_name in skill.tools:
        t = tool_map().get(tool_name)
        if t:
            tools.append(t)
        else:
            logger.warning("Skill '%s' 声明了工具 '%s'，但工具未注册", skill.name, tool_name)

    session_id = invoke_cfg.get("configurable", {}).get("thread_id", "") if invoke_cfg else ""

    agent = build_skill_agent(model, skill, tools, max_tool_calls=max_calls, session_id=session_id)

    skill_invoke_cfg = {
        **(invoke_cfg or {}),
        "recursion_limit": recursion_limit_for_tool_calls(max_calls),
    }
    result = await agent.ainvoke(
        {"messages": [HumanMessage(content=message)]},
        config=skill_invoke_cfg,
    )

    complete_data = extract_complete_result(result["messages"])
    reply = complete_data.get("summary", "") or complete_data.get("detail", "") or ""

    tokens = _extract_tokens(result)
    return reply, tokens


async def _general_response(
    message: str,
    deps: PlatformDeps,
    model_id: str | None = None,
    invoke_cfg: dict | None = None,
) -> tuple[str, dict]:
    """通用对话回复。"""
    model = deps.model_provider.get_model(model_id)
    result = await model.ainvoke(
        [
            SystemMessage(content="你是一个通用智能助手，尽力回答用户的问题。"),
            HumanMessage(content=message),
        ],
        config=invoke_cfg or {},
    )
    return result.content, _extract_tokens_from_message(result)


async def _execute_declarative_skill_direct(
    skill_name: str, message: str, deps: PlatformDeps,
    *, model_id: str | None = None, session_id: str | None = None,
) -> str:
    """跳过路由，直接执行声明式 Skill。"""
    if not deps.declarative_registry:
        return "声明式 Skill 系统未启用"

    skill = deps.declarative_registry.get(skill_name)
    if not skill:
        available = [s.name for s in (deps.declarative_registry.list_skills() or [])]
        return f"未找到声明式 Skill: {skill_name}。可用: {', '.join(available)}"

    invoke_cfg = _build_invoke_config(session_id)
    reply, _ = await _execute_declarative_skill(
        skill, message, deps, model_id, invoke_cfg
    )
    return reply


# ── 向后兼容 ──────────────────────────────────────────────────


async def route_and_execute(
    message: str,
    deps: PlatformDeps,
    *,
    model_id: str | None = None,
    session_id: str | None = None,
) -> str:
    """分析意图 + 执行决策（单次调用便捷函数）。"""
    decision = await resolve_route(message, deps, model_id=model_id)
    return await execute_decision(decision, message, deps, model_id=model_id, session_id=session_id)
