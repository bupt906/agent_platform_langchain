from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from typing import TextIO

import httpx
from httpx_sse import connect_sse

from agent_platform.config.settings import settings


DEFAULT_STREAM_URL = f"http://{settings.api_host}:{settings.api_port}/chat/stream"
CONTENT_EVENT_TYPES = {"delta", "synthesis_delta"}


def stream_chat(
    message: str,
    *,
    url: str = DEFAULT_STREAM_URL,
    agent: str | None = None,
    skill: str | None = None,
    model: str | None = None,
    session_id: str | None = None,
    show_thinking: bool = False,
    output: TextIO | None = None,
) -> None:
    """调用流式聊天接口，并将回复内容连续写入终端。"""
    stream = sys.stdout if output is None else output
    payload = {
        "message": message,
        **({"agent": agent} if agent else {}),
        **({"skill": skill} if skill else {}),
        **({"model": model} if model else {}),
        **({"session_id": session_id} if session_id else {}),
        **({"thinking": True} if show_thinking else {}),
    }

    wrote_content = False
    finished = False
    current_section = ""

    with httpx.Client(timeout=None) as client:
        with connect_sse(client, "POST", url, json=payload) as event_source:
            event_source.response.raise_for_status()

            for event in event_source.iter_sse():
                data = event.json()
                if not isinstance(data, dict):
                    continue

                event_type = data.get("type")
                if event_type == "thinking_delta":
                    if not show_thinking:
                        continue
                    content = data.get("content", "")
                    if isinstance(content, str) and content:
                        if current_section != "thinking":
                            if wrote_content:
                                stream.write("\n\n")
                            stream.write("[思考]\n")
                            current_section = "thinking"
                        stream.write(content)
                        stream.flush()
                        wrote_content = True
                elif event_type in CONTENT_EVENT_TYPES:
                    content = data.get("content", "")
                    if isinstance(content, str) and content:
                        if show_thinking and current_section != "answer":
                            if wrote_content:
                                stream.write("\n\n")
                            stream.write("[回答]\n")
                            current_section = "answer"
                        stream.write(content)
                        stream.flush()
                        wrote_content = True
                elif event_type in {"tool_start", "tool_end", "tool_error"}:
                    tool_name = data.get("tool", "unknown")
                    if event_type == "tool_start":
                        title = f"[工具调用] {tool_name}"
                        detail = data.get("input", "")
                    elif event_type == "tool_end":
                        title = f"[工具结果] {tool_name}"
                        detail = data.get("output", "")
                    else:
                        title = f"[工具错误] {tool_name}"
                        detail = data.get("error", "")
                    if wrote_content:
                        stream.write("\n\n")
                    stream.write(f"{title}\n")
                    if isinstance(detail, str) and detail:
                        stream.write(detail)
                    stream.flush()
                    wrote_content = True
                    current_section = "tool"
                elif event_type == "model_end" and show_thinking:
                    if wrote_content:
                        stream.write("\n\n")
                    stream.write(
                        "[模型结束] "
                        f"finish_reason={data.get('finish_reason', 'unknown')} "
                        f"tool_calls={data.get('tool_calls', 0)} "
                        f"invalid_tool_calls={data.get('invalid_tool_calls', 0)}"
                    )
                    stream.flush()
                    wrote_content = True
                    current_section = "model_end"
                elif event_type == "error":
                    if wrote_content:
                        stream.write("\n\n")
                    stream.write(f"[执行错误]\n{data.get('error', '未知错误')}\n")
                    stream.flush()
                    wrote_content = True
                    finished = True
                    break
                elif event_type == "done":
                    stream.write("\n")
                    stream.flush()
                    finished = True
                    break

    if not finished:
        if wrote_content:
            stream.write("\n\n")
        stream.write("[连接异常] SSE 流未收到 done 事件\n")
        stream.flush()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agent-chat",
        description="Agent Platform 流式聊天 CLI",
    )
    parser.add_argument("message", help="发送给 Agent 的消息")
    parser.add_argument(
        "--url",
        default=DEFAULT_STREAM_URL,
        help=f"流式聊天接口地址（默认：{DEFAULT_STREAM_URL}）",
    )

    target = parser.add_mutually_exclusive_group()
    target.add_argument("--agent", help="指定 Python Agent")
    target.add_argument("--skill", help="指定声明式 Skill")

    parser.add_argument("--model", help="指定模型，例如 deepseek:deepseek-chat")
    parser.add_argument("--session-id", help="指定会话 ID")
    parser.add_argument(
        "--thinking",
        action="store_true",
        help="启用并显示模型的流式思考内容",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    args = build_parser().parse_args(argv)

    try:
        stream_chat(
            args.message,
            url=args.url,
            agent=args.agent,
            skill=args.skill,
            model=args.model,
            session_id=args.session_id,
            show_thinking=args.thinking,
        )
    except KeyboardInterrupt as exc:
        print(file=sys.stderr)
        raise SystemExit(130) from exc
    except (httpx.HTTPError, ValueError) as exc:
        print(f"请求失败：{exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
