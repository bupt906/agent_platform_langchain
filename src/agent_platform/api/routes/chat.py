from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator, Iterator, Mapping
from dataclasses import dataclass, replace
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from langchain_core.messages import HumanMessage, SystemMessage
from sse_starlette.sse import EventSourceResponse

from agent_platform.api.schemas import ChatRequest, ChatResponse
from agent_platform.config.settings import settings
from agent_platform.core.deps import PlatformDeps
from agent_platform.core.router import (
    RouterDecision,
    _load_session_messages,
    execute_decision,
    execute_skill_direct,
    resolve_route,
)
from agent_platform.graph.orchestration import OrchestrationEngine

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/viewer", response_class=HTMLResponse)
async def viewer_html(path: str):
    """返回 agentcad 生成的 3D viewer.html 内容，供前端 iframe 展示。

    Args:
        path: viewer.html 的路径（相对允许根目录，如 `cad_output/v1/viewer.html`）。
    """
    from pathlib import Path

    # 解析为允许根目录内的绝对路径，防止路径穿越
    requested = Path(path).expanduser()
    if not requested.is_absolute():
        requested = Path.cwd() / requested
    resolved = requested.resolve()

    allowed_roots = [Path(r).expanduser().resolve() for r in settings.file_read_allowed_roots.split(",") if r.strip()]
    if not allowed_roots or not any(resolved.is_relative_to(root) for root in allowed_roots):
        raise HTTPException(status_code=403, detail="路径不在允许目录内")
    if resolved.suffix.lower() != ".html":
        raise HTTPException(status_code=400, detail="仅支持 .html 文件")
    if not resolved.exists():
        raise HTTPException(status_code=404, detail="viewer 文件不存在")
    return HTMLResponse(resolved.read_text(encoding="utf-8"))


@dataclass(frozen=True)
class SingleTargetResolution:
    agent: Any | None
    declarative_skill: Any | None
    target_type: str
    requested_skill: str | None = None
    fallback_reason: str | None = None


def _get_deps(request: Request) -> PlatformDeps:
    return request.app.state.deps


def _resolve_single_target(
    deps: PlatformDeps,
    skill_name: str,
    explicit_mode: str = "",
) -> SingleTargetResolution:
    """解析单路由目标；不可用或未知的声明式 Skill 降级为通用对话。"""
    if skill_name == "general" and explicit_mode != "agent":
        return SingleTargetResolution(None, None, "general")

    if explicit_mode == "agent":
        skill = deps.skill_registry.get(skill_name)
        if not skill:
            available = ", ".join(deps.skill_registry.skill_names()) or "无"
            raise ValueError(f"Python Agent '{skill_name}' 不存在；可用 Agent: {available}")
        return SingleTargetResolution(skill, None, "agent")

    if explicit_mode == "skill":
        declarative = deps.declarative_registry.get(skill_name) if deps.declarative_registry else None
        if not declarative:
            unavailable_reason = (
                deps.declarative_registry.unavailable_skills.get(skill_name) if deps.declarative_registry else None
            )
            reason = f"declarative_skill_unavailable: {unavailable_reason}" if unavailable_reason else "skill_not_found"
            logger.warning("声明式 Skill '%s' 不可用，降级为通用对话: %s", skill_name, reason)
            return SingleTargetResolution(None, None, "general", skill_name, reason)
        return SingleTargetResolution(None, declarative, "skill")

    skill = deps.skill_registry.get(skill_name)
    if skill:
        return SingleTargetResolution(skill, None, "agent")
    declarative = deps.declarative_registry.get(skill_name) if deps.declarative_registry else None
    if declarative:
        return SingleTargetResolution(None, declarative, "skill")
    if skill_name == "general":
        return SingleTargetResolution(None, None, "general")

    unavailable_reason = (
        deps.declarative_registry.unavailable_skills.get(skill_name) if deps.declarative_registry else None
    )
    reason = f"declarative_skill_unavailable: {unavailable_reason}" if unavailable_reason else "skill_not_found"
    logger.warning("自动路由目标 Skill '%s' 不可用，降级为通用对话: %s", skill_name, reason)
    return SingleTargetResolution(None, None, "general", skill_name, reason)


async def _apply_saved_preferences(body: ChatRequest, deps: PlatformDeps) -> ChatRequest:
    """Use stored model / Agent defaults only when the current request omits them."""
    if not body.profile_id or not deps.user_profile_store:
        return body
    try:
        prefs = (await deps.user_profile_store.get_profile(body.profile_id)).get("preferences", {})
        return body.model_copy(
            update={
                # Agent 仅由当前请求显式指定；未传时必须保留意图识别路径。
                "agent": body.agent,
                "model": body.model or prefs.get("default_model") or None,
            }
        )
    except Exception:
        logger.warning("读取用户偏好失败，使用请求默认值", exc_info=True)
        return body


# ── 同步对话 ────────────────────────────────────────────────────


@router.post("/chat", response_model=ChatResponse)
async def chat(request: Request, body: ChatRequest) -> ChatResponse:
    deps = _get_deps(request)
    body = await _apply_saved_preferences(body, deps)

    if body.response_mode == "general" and not body.agent and not body.skill:
        decision = RouterDecision(skill_name="general", rewritten_query=body.message, confidence=1.0)
        reply = await execute_decision(decision, body.message, deps, model_id=body.model, session_id=body.session_id)
        return ChatResponse(
            reply=reply,
            skill_used="general",
            model_used=body.model or deps.model_provider.default_model,
            session_id=body.session_id,
            requested_skill=decision.requested_skill_name,
            fallback_reason=decision.fallback_reason,
        )

    # ── 显式指定：agent / skill 二选一 ──
    if body.agent:
        reply = await execute_skill_direct(
            body.agent,
            body.message,
            deps,
            model_id=body.model,
            session_id=body.session_id,
        )
        return ChatResponse(
            reply=reply,
            skill_used=body.agent,
            model_used=body.model or deps.model_provider.default_model,
            session_id=body.session_id,
        )

    if body.skill:
        decision = RouterDecision(
            skill_name=body.skill,
            rewritten_query=body.message,
            confidence=1.0,
        )
        reply = await execute_decision(
            decision,
            body.message,
            deps,
            model_id=body.model,
            session_id=body.session_id,
        )
        return ChatResponse(
            reply=reply,
            skill_used=decision.skill_name,
            model_used=body.model or deps.model_provider.default_model,
            session_id=body.session_id,
            requested_skill=decision.requested_skill_name,
            fallback_reason=decision.fallback_reason,
        )

    # 自动路由
    decision = await resolve_route(body.message, deps, model_id=body.model)
    reply = await execute_decision(
        decision,
        body.message,
        deps,
        model_id=body.model,
        session_id=body.session_id,
    )
    return ChatResponse(
        reply=reply,
        skill_used=decision.skill_name,
        model_used=body.model or deps.model_provider.default_model,
        session_id=body.session_id,
        requested_skill=decision.requested_skill_name,
        fallback_reason=decision.fallback_reason,
    )


# ── 流式对话 ────────────────────────────────────────────────────


@router.post("/chat/stream")
async def chat_stream(request: Request, body: ChatRequest) -> EventSourceResponse:
    deps = _get_deps(request)

    async def event_generator():
        effective_body = await _apply_saved_preferences(body, deps)
        # 使用请求级 provider 视图，避免修改全局模型配置或影响其他并发请求。
        stream_deps = replace(
            deps,
            model_provider=deps.model_provider.with_thinking(effective_body.thinking),
        )
        model_info = stream_deps.model_provider.describe_public_model(effective_body.model)
        yield _sse("model_info", type="model_info", **model_info)

        # ── 显式指定 agent / skill / 自动路由 ──
        explicit_mode = ""
        if effective_body.agent:
            skill_name = effective_body.agent
            explicit_mode = "agent"
            decision = None
        elif effective_body.skill:
            skill_name = effective_body.skill
            explicit_mode = "skill"
            decision = None
        elif effective_body.response_mode == "auto":
            decision = await resolve_route(effective_body.message, deps, model_id=effective_body.model)
            skill_name = decision.skill_name
        else:
            skill_name = "general"
            decision = None

        # ── 多 Agent 编排流式 ──
        is_multi = decision and decision.mode == "multi" and decision.execution_plan
        if is_multi:
            yield _sse(
                "routing",
                type="routing",
                source="auto",
                target_type="multi",
                skill="multi_agent",
                mode=decision.mode,
                confidence=decision.confidence,
            )
            plan = decision.execution_plan
            yield _sse("plan", type="plan", mode=plan.mode, subtasks=[s.model_dump() for s in plan.subtasks])

            engine = OrchestrationEngine(stream_deps)
            async for event in engine.execute_stream(effective_body.message, plan):
                yield _sse(event.type, **event.to_dict())

            yield _sse("done", type="done", skill="multi_agent")
            return

        # ── 单技能 / 通用流式 ──
        target = _resolve_single_target(
            deps,
            skill_name,
            explicit_mode,
        )
        skill = target.agent
        declarative = target.declarative_skill
        target_type = target.target_type
        requested_skill = target.requested_skill
        fallback_reason = target.fallback_reason
        declarative_tools = []
        if declarative:
            from agent_platform.skills.builder import resolve_skill_tools
            from agent_platform.tools.registry import tool_map

            try:
                declarative_tools = resolve_skill_tools(declarative, tool_map())
            except RuntimeError as exc:
                logger.warning(
                    "声明式 Skill '%s' 配置无效，降级为通用对话: %s",
                    skill_name,
                    exc,
                )
                skill = None
                declarative = None
                target_type = "general"
                requested_skill = skill_name
                fallback_reason = f"declarative_skill_configuration_error: {exc}"
        if target_type == "general":
            skill_name = "general"
        yield _sse(
            "routing",
            type="routing",
            source="explicit" if explicit_mode else "auto",
            target_type=target_type,
            skill=skill_name,
            mode=decision.mode if decision else "single",
            confidence=decision.confidence if decision else 1.0,
            tools=[tool.name for tool in declarative_tools],
            requested_skill=requested_skill,
            fallback_reason=fallback_reason,
        )

        if not skill and not declarative:
            # 通用对话
            model = stream_deps.model_provider.get_model(effective_body.model)
            identity = stream_deps.model_provider.model_identity_instruction(effective_body.model)
            async for chunk in model.astream(
                [
                    SystemMessage(content=(f"你是一个通用智能助手，尽力回答用户的问题。\n\n{identity}")),
                    HumanMessage(content=effective_body.message),
                ]
            ):
                for event_type, content in _chunk_deltas(chunk):
                    yield _sse(
                        event_type,
                        type=event_type,
                        content=content,
                    )

        elif declarative:
            # 声明式 Skill → 动态构建 Agent
            from agent_platform.skills.builder import (
                build_skill_agent,
                recursion_limit_for_tool_calls,
            )

            model = stream_deps.model_provider.get_model(effective_body.model)
            from agent_platform.config.settings import settings as _settings

            max_calls = _settings.declarative_skills_max_tool_calls

            from uuid import uuid4

            invoke_cfg = {
                "configurable": {"thread_id": effective_body.session_id or uuid4().hex},
                "recursion_limit": recursion_limit_for_tool_calls(max_calls),
            }
            agent = build_skill_agent(
                model,
                declarative,
                declarative_tools,
                max_tool_calls=max_calls,
                session_id=effective_body.session_id or "",
                model_identity=stream_deps.model_provider.model_identity_instruction(effective_body.model),
            )

            # 加载会话历史，让 skill 感知多轮上下文
            history_messages = await _load_session_messages(
                deps, effective_body.session_id or ""
            )
            input_messages = [*history_messages, HumanMessage(content=effective_body.message)]

            final_reply = ""
            try:
                async for event in agent.astream_events(
                    {"messages": input_messages},
                    version="v2",
                    config=invoke_cfg,
                ):
                    if event["event"] == "on_chat_model_stream":
                        for event_type, content in _chunk_deltas(event["data"]["chunk"]):
                            yield _sse(
                                event_type,
                                type=event_type,
                                content=content,
                            )
                    else:
                        # 检测 agentcad run 生成的 viewer，发给前端展示
                        # 必须在 tool_event 判断之前，确保 complete_task 的
                        # on_tool_start（含 VIEWER_PATH）也能被检测到。
                        viewer_path = _extract_viewer_path(event)
                        if viewer_path:
                            yield _sse("cad_viewer", type="cad_viewer", path=viewer_path)

                        tool_event = _tool_event_data(event)
                        if tool_event:
                            event_type, data = tool_event
                            yield _sse(event_type, **data)
                        elif event["event"] == "on_chat_model_end":
                            yield _sse("model_end", **_model_end_data(event))

                        reply_part = _extract_final_reply(event)
                        if reply_part:
                            final_reply = reply_part
            except Exception as exc:
                logger.exception("声明式 Skill '%s' 流式执行失败", declarative.name)
                yield _sse(
                    "error",
                    type="error",
                    error=f"{type(exc).__name__}: {exc}",
                )
                return

            # 持久化本轮对话，多轮记忆才能生效
            if deps.session_store and effective_body.session_id:
                try:
                    await deps.session_store.add_turn(
                        session_id=effective_body.session_id,
                        user_message=effective_body.message,
                        assistant_message=final_reply or "",
                        skill_used=skill_name,
                        tokens_used=0,
                    )
                except Exception:
                    logger.warning("流式持久化对话记录失败", exc_info=True)

        else:
            # 使用 Python Agent
            skills = deps.skill_registry.get_all_skills()
            agent = skill.compose(skills, stream_deps.model_provider) or skill.create_agent(
                stream_deps.model_provider, checkpointer=deps.checkpointer
            )
            query = decision.rewritten_query if decision else effective_body.message

            from uuid import uuid4

            invoke_cfg = {"configurable": {"thread_id": effective_body.session_id or uuid4().hex}}

            async for event in agent.astream_events(
                {"messages": [HumanMessage(content=query)]},
                version="v2",
                config=invoke_cfg,
            ):
                if event["event"] == "on_chat_model_stream":
                    for event_type, content in _chunk_deltas(event["data"]["chunk"]):
                        yield _sse(
                            event_type,
                            type=event_type,
                            content=content,
                        )
                else:
                    tool_event = _tool_event_data(event)
                    if tool_event:
                        event_type, data = tool_event
                        yield _sse(event_type, **data)
                    elif event["event"] == "on_chat_model_end":
                        yield _sse("model_end", **_model_end_data(event))

        yield _sse("done", type="done", skill=skill_name)

    return EventSourceResponse(_guard_sse_stream(event_generator()))


# ── SSE 辅助 ────────────────────────────────────────────────────


async def _guard_sse_stream(
    events: AsyncIterator[dict[str, Any]],
) -> AsyncIterator[dict[str, Any]]:
    """把未捕获的流式异常转换成客户端可见的 error 事件。"""
    try:
        async for event in events:
            yield event
    except Exception as exc:
        logger.exception("聊天 SSE 流异常终止")
        yield _sse(
            "error",
            type="error",
            error=f"{type(exc).__name__}: {exc}",
        )


def _chunk_deltas(chunk: Any) -> Iterator[tuple[str, str]]:
    """将 LangChain 消息块拆分为思考和最终回答 SSE 增量。"""
    for block in chunk.content_blocks:
        block_type = block.get("type")
        if block_type == "reasoning":
            reasoning = block.get("reasoning")
            if isinstance(reasoning, str) and reasoning:
                yield "thinking_delta", reasoning
        elif block_type == "text":
            text = block.get("text")
            if isinstance(text, str) and text:
                yield "delta", text


def _compact_tool_value(value: Any, *, depth: int = 0) -> Any:
    """压缩工具事件数据，避免大段 write_file 内容占满 SSE/终端。"""
    if depth >= 4:
        return "<max depth>"
    if isinstance(value, str):
        if len(value) <= 500:
            return value
        return f"{value[:300]}… <{len(value)} chars>"
    if isinstance(value, Mapping):
        items = list(value.items())
        compact = {str(key): _compact_tool_value(item, depth=depth + 1) for key, item in items[:30]}
        if len(items) > 30:
            compact["<omitted>"] = f"{len(items) - 30} fields"
        return compact
    if isinstance(value, (list, tuple)):
        compact = [_compact_tool_value(item, depth=depth + 1) for item in value[:20]]
        if len(value) > 20:
            compact.append(f"<{len(value) - 20} items omitted>")
        return compact
    if hasattr(value, "content"):
        return _compact_tool_value(value.content, depth=depth + 1)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return _compact_tool_value(str(value), depth=depth + 1)


def _tool_preview(value: Any) -> str:
    compact = _compact_tool_value(value)
    if isinstance(compact, str):
        return compact
    return json.dumps(compact, ensure_ascii=False, default=str)


def _extract_viewer_path(event: Mapping[str, Any]) -> str:
    """从工具事件中提取 agentcad run 生成的 viewer 路径，供前端 iframe 展示。

    两条来源：
    1. bash 工具 on_tool_end：输出是 `{"success":..., "stdout":...}` 的 JSON，
       其中 `stdout` 里才是 agentcad run 的 JSON（含 `viewer` 字段）。
    2. complete_task 工具 on_tool_start：输入里的 detail 含 `VIEWER_PATH: xxx` 行。
    """
    data = event.get("data") or {}
    event_name = event.get("event")

    candidate = ""
    if event_name == "on_tool_end":
        candidate = data.get("output")
    elif event_name == "on_tool_start":
        candidate = data.get("input")
    if candidate is None:
        return ""

    # on_tool_end 的 output 可能是 ToolMessage，取其 .content（才是 JSON 字符串）
    if not isinstance(candidate, (str, dict)):
        try:
            candidate = candidate.content
        except Exception:
            pass
    text = candidate if isinstance(candidate, str) else str(candidate)

    # 第一层：外层 JSON（bash 包装 或 complete_task input JSON）
    inner_text = text
    try:
        outer = json.loads(text)
        if isinstance(outer, dict):
            if outer.get("viewer"):
                return str(outer["viewer"])
            inner_text = outer.get("stdout") or outer.get("detail") or outer.get("content") or inner_text
    except (json.JSONDecodeError, TypeError):
        if isinstance(candidate, dict):
            inner_text = candidate.get("detail") or candidate.get("content") or str(candidate)

    # 第二层：agentcad run 的 JSON
    try:
        inner = json.loads(inner_text)
        if isinstance(inner, dict) and inner.get("viewer"):
            return str(inner["viewer"])
    except (json.JSONDecodeError, TypeError):
        pass

    # 兜底：找 VIEWER_PATH: xxx 行
    for line in inner_text.splitlines():
        line = line.strip()
        if line.startswith("VIEWER_PATH:"):
            return line.split(":", 1)[1].strip()
    return ""


def _extract_final_reply(event: Mapping[str, Any]) -> str:
    """从 complete_task 工具事件中提取最终回复（summary）。

    声明式 Skill 的最终结果由 complete_task 的 summary 承载。流式路径
    需要它来持久化多轮对话历史（add_turn）。
    """
    if event.get("event") != "on_tool_start":
        return ""
    if str(event.get("name") or "") != "complete_task":
        return ""
    data = event.get("data") or {}
    candidate = data.get("input")
    if candidate is None:
        return ""
    if not isinstance(candidate, (str, dict)):
        try:
            candidate = candidate.content
        except Exception:
            pass
    if isinstance(candidate, dict):
        return str(candidate.get("summary") or "")
    try:
        parsed = json.loads(candidate)
        if isinstance(parsed, dict):
            return str(parsed.get("summary") or "")
    except (json.JSONDecodeError, TypeError):
        pass
    return ""


def _tool_event_data(event: Mapping[str, Any]) -> tuple[str, dict[str, Any]] | None:
    """把 LangChain 工具事件转换成可供 CLI 展示的 SSE 数据。"""
    event_name = event.get("event")
    tool_name = str(event.get("name") or "unknown")
    data = event.get("data") or {}
    if event_name == "on_tool_start":
        return "tool_start", {
            "type": "tool_start",
            "tool": tool_name,
            "input": _tool_preview(data.get("input")),
        }
    if event_name == "on_tool_end":
        return "tool_end", {
            "type": "tool_end",
            "tool": tool_name,
            "output": _tool_preview(data.get("output")),
        }
    if event_name == "on_tool_error":
        return "tool_error", {
            "type": "tool_error",
            "tool": tool_name,
            "error": _tool_preview(data.get("error")),
        }
    return None


def _model_end_data(event: Mapping[str, Any]) -> dict[str, Any]:
    """提取模型轮次终止原因，供 --thinking 模式诊断提前结束。"""
    data = event.get("data") or {}
    output = data.get("output")
    metadata = getattr(output, "response_metadata", {}) or {}
    tool_calls = getattr(output, "tool_calls", []) or []
    invalid_tool_calls = getattr(output, "invalid_tool_calls", []) or []
    result = {
        "type": "model_end",
        "finish_reason": metadata.get("finish_reason", "unknown"),
        "tool_calls": len(tool_calls),
        "invalid_tool_calls": len(invalid_tool_calls),
    }
    reported_model = metadata.get("model_name") or metadata.get("model")
    if reported_model:
        result["reported_model"] = reported_model
    return result


def _sse(event: str, **data) -> dict:
    """构建 SSE 事件 dict。"""
    return {
        "event": event,
        "data": json.dumps(data, ensure_ascii=False),
    }
