from __future__ import annotations

import argparse
import os
import shlex
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from typing import TextIO
from uuid import uuid4

import httpx
from httpx_sse import connect_sse

from agent_platform.config.settings import settings


DEFAULT_STREAM_URL = f"http://{settings.api_host}:{settings.api_port}/chat/stream"
CONTENT_EVENT_TYPES = {"delta", "synthesis_delta"}
MODEL_PRESETS = tuple(
    dict.fromkeys(
        (
            settings.default_model,
            "volcengine:ark-code-latest",
            "deepseek:deepseek-v4-pro",
            "qwen:qwen-plus",
            "openai:gpt-4o",
            "ollama:llama3",
        )
    )
)
SLASH_COMMANDS = (
    "/model",
    "/agent",
    "/skill",
    "/auto",
    "/thinking",
    "/session",
    "/new",
    "/status",
    "/whoami",
    "/url",
    "/clear",
    "/help",
    "/exit",
)

_RESET = "\033[0m"
_BOLD = "\033[1m"
_DIM = "\033[2m"
_CYAN = "\033[36m"
_GREEN = "\033[32m"
_YELLOW = "\033[33m"
_RED = "\033[31m"


@dataclass
class CLIState:
    """交互模式中可随时修改的会话配置。"""

    url: str = DEFAULT_STREAM_URL
    agent: str | None = None
    skill: str | None = None
    model: str | None = None
    session_id: str | None = None
    show_thinking: bool = False

    @property
    def effective_model(self) -> str:
        return self.model or settings.default_model

    @property
    def target(self) -> str:
        if self.agent:
            return f"agent:{self.agent}"
        if self.skill:
            return f"skill:{self.skill}"
        return "自动路由"


def _supports_color(stream: TextIO) -> bool:
    return os.environ.get("NO_COLOR") is None and bool(getattr(stream, "isatty", lambda: False)())


def _styled(text: str, *codes: str, enabled: bool) -> str:
    if not enabled:
        return text
    return f"{''.join(codes)}{text}{_RESET}"


def _readline_styled(text: str, *codes: str, enabled: bool) -> str:
    """为 input/readline 标记 ANSI 非打印片段，避免光标列计算错位。"""
    if not enabled:
        return text
    # GNU Readline 使用 SOH/STX 包住零宽控制序列；这两个标记不会显示。
    prefix = f"\001{''.join(codes)}\002"
    suffix = f"\001{_RESET}\002"
    return f"{prefix}{text}{suffix}"


def _new_session_id() -> str:
    return f"cli-{uuid4().hex[:8]}"


def _package_version() -> str:
    try:
        return version("agent-platform-langchain")
    except PackageNotFoundError:
        return "0.1.0"


def _enable_line_editing() -> None:
    """可用时启用方向键历史与斜杠命令补全。"""
    try:
        import readline
    except ImportError:  # pragma: no cover - Windows 等无 readline 环境
        return

    def complete(text: str, index: int) -> str | None:
        matches = [command for command in SLASH_COMMANDS if command.startswith(text)]
        return matches[index] if index < len(matches) else None

    readline.set_auto_history(True)
    readline.set_completer(complete)
    readline.parse_and_bind("tab: complete")


def stream_chat(
    message: str,
    *,
    url: str = DEFAULT_STREAM_URL,
    agent: str | None = None,
    skill: str | None = None,
    model: str | None = None,
    session_id: str | None = None,
    show_thinking: bool = False,
    show_model_info: bool = False,
    show_routing: bool = False,
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
                if event_type == "model_info":
                    if not show_model_info:
                        continue
                    model_id = data.get("model_id", "unknown")
                    base_url = data.get("base_url", "unknown")
                    api_mode = data.get("api_mode", "unknown")
                    stream.write(f"[模型] {model_id}\n")
                    stream.write(f"[Endpoint] {base_url} ({api_mode})\n")
                    stream.flush()
                    wrote_content = True
                    current_section = "model_info"
                elif event_type == "routing":
                    if not show_routing:
                        continue
                    source = "手动" if data.get("source") == "explicit" else "自动"
                    target_type = data.get("target_type", "unknown")
                    skill_name = data.get("skill", "unknown")
                    confidence = data.get("confidence")
                    suffix = f" · confidence={confidence:.2f}" if isinstance(confidence, (int, float)) else ""
                    tools = data.get("tools")
                    if isinstance(tools, list) and tools:
                        suffix += f" · tools={','.join(str(name) for name in tools)}"
                    stream.write(f"[路由] {source} → {target_type}:{skill_name}{suffix}\n")
                    stream.flush()
                    wrote_content = True
                    current_section = "routing"
                elif event_type == "thinking_delta":
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
                    if data.get("reported_model"):
                        stream.write(f" reported_model={data['reported_model']}")
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


def _print_banner(state: CLIState, stream: TextIO, *, color: bool) -> None:
    title = _styled("Agent Platform", _BOLD, _CYAN, enabled=color)
    meta = f"model: {state.effective_model}  ·  target: {state.target}  ·  session: {state.session_id or '关闭'}"
    print(f"\n{title}", file=stream)
    print(_styled(meta, _DIM, enabled=color), file=stream)
    print("输入消息开始对话，/help 查看命令，/exit 退出。\n", file=stream)


def _print_help(stream: TextIO, *, color: bool) -> None:
    heading = _styled("交互命令", _BOLD, enabled=color)
    rows = (
        ("/model [编号|模型ID|default]", "查看或切换模型"),
        ("/agent <名称> [问题]", "指定 Python Agent；可在同一行直接提问"),
        ("/skill <名称> [问题]", "指定声明式 Skill；可在同一行直接提问"),
        ("/auto", "恢复自动路由"),
        ("/thinking [on|off]", "开关思考内容"),
        ("/session [ID|new|off]", "查看、切换或关闭会话记忆"),
        ("/new", "创建新会话，保留模型和路由设置"),
        ("/status", "显示当前配置"),
        ("/whoami", "显示请求模型、Provider 和 Endpoint"),
        ("/url [地址|default]", "查看或切换 API 地址"),
        ("/clear", "清屏"),
        ("/help", "显示本帮助"),
        ("/exit", "退出"),
    )
    print(heading, file=stream)
    for command, description in rows:
        rendered = _styled(f"  {command:<30}", _CYAN, enabled=color)
        print(f"{rendered}{description}", file=stream)
    print("\n提示：输入 //help 会把 /help 作为普通消息发送。", file=stream)


def _print_models(state: CLIState, stream: TextIO, *, color: bool) -> None:
    print(_styled("可用模型", _BOLD, enabled=color), file=stream)
    print(f"  当前：{state.effective_model}\n", file=stream)
    for index, model_id in enumerate(MODEL_PRESETS, start=1):
        marker = "●" if model_id == state.effective_model else " "
        suffix = "（默认）" if model_id == settings.default_model else ""
        print(f"  {marker} {index}. {model_id} {suffix}".rstrip(), file=stream)
    print("\n使用 /model <编号> 或 /model <provider:model> 切换。", file=stream)


def _print_status(state: CLIState, stream: TextIO, *, color: bool) -> None:
    model = state.effective_model
    if state.model is None:
        model += "（默认）"
    thinking = "开启" if state.show_thinking else "关闭"
    print(_styled("当前配置", _BOLD, enabled=color), file=stream)
    print(f"  模型    {model}", file=stream)
    print(f"  路由    {state.target}", file=stream)
    print(f"  会话    {state.session_id or '关闭'}", file=stream)
    print(f"  思考    {thinking}", file=stream)
    print(f"  API     {state.url}", file=stream)


def _command_value(parts: list[str]) -> str:
    return " ".join(parts[1:]).strip()


def _prepare_inline_target_message(
    line: str,
    state: CLIState,
    *,
    output: TextIO,
) -> str | None:
    """解析 ``/skill NAME 问题`` 与 ``/agent NAME 问题`` 一行调用语法。"""
    try:
        parts = shlex.split(line)
    except ValueError:
        return None
    if len(parts) < 3:
        return None

    command = parts[0].lower()
    target_name = parts[1]
    if target_name.lower() in {"auto", "off", "none"}:
        return None

    if command in {"/skill", "/s"}:
        state.skill = target_name
        state.agent = None
        print(f"Skill 已切换：{state.skill}", file=output)
    elif command in {"/agent", "/a"}:
        state.agent = target_name
        state.skill = None
        print(f"Agent 已切换：{state.agent}", file=output)
    else:
        return None

    return " ".join(parts[2:]).strip()


def handle_command(
    line: str,
    state: CLIState,
    *,
    output: TextIO,
    color: bool = False,
) -> bool:
    """执行一条斜杠命令。返回 False 表示退出交互模式。"""
    try:
        parts = shlex.split(line)
    except ValueError as exc:
        print(_styled(f"命令格式错误：{exc}", _RED, enabled=color), file=output)
        return True

    if not parts:
        return True

    command = parts[0].lower()
    value = _command_value(parts)

    if command in {"/exit", "/quit", "/q"}:
        return False
    if command in {"/help", "/h", "/?"}:
        _print_help(output, color=color)
    elif command in {"/status", "/config"}:
        _print_status(state, output, color=color)
    elif command == "/whoami":
        from agent_platform.models.provider import ModelProvider

        try:
            info = ModelProvider(settings).describe_model(state.model)
        except ValueError as exc:
            print(_styled(f"模型配置错误：{exc}", _RED, enabled=color), file=output)
        else:
            print(_styled("模型连接", _BOLD, enabled=color), file=output)
            print(f"  请求模型  {info['model_id']}", file=output)
            print(f"  Provider  {info['provider_name']} ({info['provider']})", file=output)
            print(f"  Endpoint  {info['base_url']}", file=output)
            print(f"  API 模式  {info['api_mode']}", file=output)
    elif command in {"/model", "/models", "/m"}:
        if not value:
            _print_models(state, output, color=color)
        elif value.lower() in {"default", "auto"}:
            state.model = None
            print(f"模型已恢复默认：{settings.default_model}", file=output)
        elif value.isdigit() and 1 <= int(value) <= len(MODEL_PRESETS):
            state.model = MODEL_PRESETS[int(value) - 1]
            print(f"模型已切换：{state.model}", file=output)
        elif value.isdigit():
            print(f"模型编号应在 1-{len(MODEL_PRESETS)} 之间。", file=output)
        else:
            state.model = value
            print(f"模型已切换：{state.model}", file=output)
    elif command in {"/agent", "/a"}:
        if not value:
            print(f"当前 Agent：{state.agent or '自动路由'}", file=output)
        elif value.lower() in {"auto", "off", "none"}:
            state.agent = None
            state.skill = None
            print("Agent 已清除，当前使用自动路由。", file=output)
        else:
            state.agent = value
            state.skill = None
            print(f"Agent 已切换：{state.agent}", file=output)
    elif command in {"/skill", "/s"}:
        if not value:
            print(f"当前 Skill：{state.skill or '自动路由'}", file=output)
        elif value.lower() in {"auto", "off", "none"}:
            state.skill = None
            state.agent = None
            print("Skill 已清除，当前使用自动路由。", file=output)
        else:
            state.skill = value
            state.agent = None
            print(f"Skill 已切换：{state.skill}", file=output)
    elif command == "/auto":
        state.agent = None
        state.skill = None
        print("已恢复自动路由。", file=output)
    elif command in {"/thinking", "/think", "/t"}:
        normalized = value.lower()
        if normalized in {"on", "true", "1"}:
            state.show_thinking = True
        elif normalized in {"off", "false", "0"}:
            state.show_thinking = False
        elif not normalized or normalized == "toggle":
            state.show_thinking = not state.show_thinking
        else:
            print("用法：/thinking [on|off]", file=output)
            return True
        status = "开启" if state.show_thinking else "关闭"
        print(f"思考内容已{status}。", file=output)
    elif command in {"/session", "/session-id"}:
        normalized = value.lower()
        if not value:
            print(f"当前会话：{state.session_id or '关闭'}", file=output)
        elif normalized in {"new", "reset"}:
            state.session_id = _new_session_id()
            print(f"已创建新会话：{state.session_id}", file=output)
        elif normalized in {"off", "none"}:
            state.session_id = None
            print("会话记忆已关闭。", file=output)
        else:
            state.session_id = value
            print(f"已切换会话：{state.session_id}", file=output)
    elif command == "/new":
        state.session_id = _new_session_id()
        print(f"已创建新会话：{state.session_id}", file=output)
    elif command == "/url":
        if not value:
            print(f"当前 API：{state.url}", file=output)
        elif value.lower() == "default":
            state.url = DEFAULT_STREAM_URL
            print(f"API 已恢复默认：{state.url}", file=output)
        elif value.startswith(("http://", "https://")):
            state.url = value
            print(f"API 已切换：{state.url}", file=output)
        else:
            print("API 地址必须以 http:// 或 https:// 开头。", file=output)
    elif command == "/clear":
        if getattr(output, "isatty", lambda: False)():
            output.write("\033[2J\033[H")
            output.flush()
        else:
            print("\n" + "─" * 48, file=output)
    else:
        print(
            _styled(f"未知命令：{command}。输入 /help 查看可用命令。", _YELLOW, enabled=color),
            file=output,
        )
    return True


def _prompt(state: CLIState, *, color: bool) -> str:
    model_name = state.effective_model
    if len(model_name) > 32:
        model_name = model_name[:29] + "…"
    label = _readline_styled("you", _BOLD, _GREEN, enabled=color)
    return f"{label} [{model_name}] › "


def run_interactive(
    *,
    url: str = DEFAULT_STREAM_URL,
    agent: str | None = None,
    skill: str | None = None,
    model: str | None = None,
    session_id: str | None = None,
    show_thinking: bool = False,
    first_message: str | None = None,
    no_color: bool = False,
    input_func: Callable[[str], str] | None = None,
    output: TextIO | None = None,
    error: TextIO | None = None,
) -> None:
    """启动轻量交互式聊天，可通过斜杠命令动态修改会话配置。"""
    out = sys.stdout if output is None else output
    err = sys.stderr if error is None else error
    read = input if input_func is None else input_func
    if input_func is None:
        _enable_line_editing()
    color = not no_color and _supports_color(out)
    state = CLIState(
        url=url,
        agent=agent,
        skill=skill,
        model=model,
        session_id=session_id or _new_session_id(),
        show_thinking=show_thinking,
    )
    _print_banner(state, out, color=color)

    pending_message = first_message
    while True:
        if pending_message is not None:
            line = pending_message
            pending_message = None
        else:
            try:
                line = read(_prompt(state, color=color))
            except EOFError:
                print("\n再见。", file=out)
                break
            except KeyboardInterrupt:
                print("\n已取消输入；输入 /exit 退出。", file=out)
                continue

        line = line.strip()
        if not line:
            continue
        if line.startswith("//"):
            line = line[1:]
        elif line.startswith("/"):
            inline_message = _prepare_inline_target_message(
                line,
                state,
                output=out,
            )
            if inline_message is None:
                if not handle_command(line, state, output=out, color=color):
                    print("再见。", file=out)
                    break
                continue
            line = inline_message

        assistant = _styled("assistant", _BOLD, _CYAN, enabled=color)
        print(f"\n{assistant} › ", end="", file=out, flush=True)
        try:
            stream_chat(
                line,
                url=state.url,
                agent=state.agent,
                skill=state.skill,
                model=state.model,
                session_id=state.session_id,
                show_thinking=state.show_thinking,
                show_model_info=True,
                show_routing=True,
                output=out,
            )
        except KeyboardInterrupt:
            print("\n已取消当前请求。", file=err)
        except (httpx.HTTPError, ValueError) as exc:
            print(_styled(f"\n请求失败：{exc}", _RED, enabled=color), file=err)
        print(file=out)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agent-chat",
        description="Agent Platform 轻量交互式 CLI",
        epilog=(
            "示例：\n"
            "  agent-chat                         进入交互模式\n"
            "  agent-chat '帮我审查这份合同'       单次提问\n"
            "  agent-chat -m deepseek:deepseek-v4-pro '你好'\n"
            "  agent-chat -i '先分析这个问题'       提问后继续交互"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "message",
        nargs="?",
        help="发送给 Agent 的消息；省略时进入交互模式",
    )
    parser.add_argument(
        "--url",
        default=DEFAULT_STREAM_URL,
        help=f"流式聊天接口地址（默认：{DEFAULT_STREAM_URL}）",
    )

    target = parser.add_mutually_exclusive_group()
    target.add_argument("-a", "--agent", help="指定 Python Agent")
    target.add_argument("-s", "--skill", help="指定声明式 Skill")

    parser.add_argument("-m", "--model", help="指定模型，例如 deepseek:deepseek-v4-pro")
    parser.add_argument("--session-id", "--session", help="指定会话 ID")
    parser.add_argument(
        "-t",
        "--thinking",
        action="store_true",
        help="启用并显示模型的流式思考内容",
    )
    parser.add_argument(
        "-i",
        "--interactive",
        action="store_true",
        help="发送首条消息后继续交互",
    )
    parser.add_argument("--no-color", action="store_true", help="关闭交互界面颜色")
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {_package_version()}",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    args = build_parser().parse_args(argv)

    if args.message is None or args.interactive:
        run_interactive(
            url=args.url,
            agent=args.agent,
            skill=args.skill,
            model=args.model,
            session_id=args.session_id,
            show_thinking=args.thinking,
            first_message=args.message,
            no_color=args.no_color,
        )
        return

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
