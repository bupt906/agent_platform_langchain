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
5. confidence 是你对路由决策的置信度 (0.0-1.0)"""


async def resolve_route(
    message: str,
    deps: PlatformDeps,
    *,
    model_id: str | None = None,
) -> RouterDecision:
    """分析用户意图，返回路由决策。chat 端点的共享入口。"""
    model = deps.model_provider.get_model(model_id)
    structured_model = model.with_structured_output(RouterDecision)

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
                result = await agent.ainvoke(
                    {"messages": [HumanMessage(content=decision.rewritten_query)]},
                    config=invoke_cfg,
                )
                reply = result["messages"][-1].content
            else:
                # 检查技能手册匹配
                manual_name: str | None = None
                if deps.manual_registry:
                    matched = deps.manual_registry.match(message)
                    if matched:
                        manual_name = matched.name
                        decision.skill_name = f"manual:{matched.name}"
                reply = await _general_response(
                    message, deps, model_id, invoke_cfg, manual_name=manual_name
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
    """跳过路由，直接调用指定技能。"""
    invoke_cfg = _build_invoke_config(session_id)
    skill = deps.skill_registry.get(skill_name)
    if not skill:
        return f"未找到技能: {skill_name}"

    start_time = time.monotonic()
    reply = ""
    error = None

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
    return {}


async def _general_response(
    message: str,
    deps: PlatformDeps,
    model_id: str | None = None,
    invoke_cfg: dict | None = None,
    *,
    manual_name: str | None = None,
) -> str:
    """通用对话回复，可选注入技能手册内容。"""
    system_content = "你是一个通用智能助手，尽力回答用户的问题。"

    # ── 技能手册注入 ──
    if deps.manual_registry and deps.manual_registry.count > 0:
        # 按指定名称获取，或自动匹配
        manual_prompt = None
        if manual_name:
            manual_prompt = deps.manual_registry.get_prompt_text(manual_name)
        else:
            manual_prompt = deps.manual_registry.get_prompt_text(message)

        if manual_prompt:
            system_content += f"\n\n{manual_prompt}"
            logger.info("注入技能手册: %s", manual_name or "自动匹配")

    model = deps.model_provider.get_model(model_id)
    result = await model.ainvoke(
        [
            SystemMessage(content=system_content),
            HumanMessage(content=message),
        ],
        config=invoke_cfg or {},
    )
    return result.content


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
