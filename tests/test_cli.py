from __future__ import annotations

from io import StringIO

from agent_platform import cli
from agent_platform.config.settings import settings


class FakeResponse:
    def __init__(self) -> None:
        self.checked = False

    def raise_for_status(self) -> None:
        self.checked = True


class FakeEvent:
    def __init__(self, data: object) -> None:
        self._data = data

    def json(self) -> object:
        return self._data


class FakeEventSource:
    def __init__(self, events: list[FakeEvent]) -> None:
        self.events = events
        self.response = FakeResponse()

    def __enter__(self) -> "FakeEventSource":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def iter_sse(self):
        yield from self.events


def test_default_stream_url_uses_api_settings() -> None:
    assert cli.DEFAULT_STREAM_URL == (f"http://{settings.api_host}:{settings.api_port}/chat/stream")


def test_stream_chat_prints_content_without_token_newlines(monkeypatch) -> None:
    source = FakeEventSource(
        [
            FakeEvent({"type": "routing", "skill": "qa"}),
            FakeEvent({"type": "delta", "content": "你"}),
            FakeEvent({"type": "delta", "content": "好"}),
            FakeEvent({"type": "done", "skill": "qa"}),
        ]
    )
    request = {}

    def fake_connect_sse(client, method, url, **kwargs):
        request.update(method=method, url=url, **kwargs)
        return source

    monkeypatch.setattr(cli, "connect_sse", fake_connect_sse)
    output = StringIO()

    cli.stream_chat(
        "打招呼",
        skill="qa",
        model="test:model",
        session_id="session-1",
        output=output,
    )

    assert output.getvalue() == "你好\n"
    assert source.response.checked is True
    assert request == {
        "method": "POST",
        "url": cli.DEFAULT_STREAM_URL,
        "json": {
            "message": "打招呼",
            "skill": "qa",
            "model": "test:model",
            "session_id": "session-1",
        },
    }


def test_stream_chat_prints_multi_agent_synthesis(monkeypatch) -> None:
    source = FakeEventSource(
        [
            FakeEvent({"type": "step_start", "description": "分析"}),
            FakeEvent({"type": "synthesis_delta", "content": "综合"}),
            FakeEvent({"type": "synthesis_delta", "content": "结果"}),
            FakeEvent({"type": "done"}),
        ]
    )
    monkeypatch.setattr(cli, "connect_sse", lambda *args, **kwargs: source)
    output = StringIO()

    cli.stream_chat("分析任务", output=output)

    assert output.getvalue() == "综合结果\n"


def test_stream_chat_prints_authoritative_model_connection(monkeypatch) -> None:
    source = FakeEventSource(
        [
            FakeEvent(
                {
                    "type": "model_info",
                    "model_id": "deepseek:deepseek-v4-pro",
                    "base_url": "https://api.deepseek.com/",
                    "api_mode": "openai-chat-completions",
                }
            ),
            FakeEvent({"type": "delta", "content": "回答"}),
            FakeEvent({"type": "done"}),
        ]
    )
    monkeypatch.setattr(cli, "connect_sse", lambda *args, **kwargs: source)
    output = StringIO()

    cli.stream_chat("测试", show_model_info=True, output=output)

    assert output.getvalue() == (
        "[模型] deepseek:deepseek-v4-pro\n[Endpoint] https://api.deepseek.com/ (openai-chat-completions)\n回答\n"
    )


def test_stream_chat_prints_selected_route(monkeypatch) -> None:
    source = FakeEventSource(
        [
            FakeEvent(
                {
                    "type": "routing",
                    "source": "auto",
                    "target_type": "skill",
                    "skill": "knowledge-graph-extraction",
                    "confidence": 0.98,
                    "tools": ["read_file", "write_file", "edit_file", "bash"],
                }
            ),
            FakeEvent({"type": "delta", "content": "完成"}),
            FakeEvent({"type": "done"}),
        ]
    )
    monkeypatch.setattr(cli, "connect_sse", lambda *args, **kwargs: source)
    output = StringIO()

    cli.stream_chat("抽取知识图谱", show_routing=True, output=output)

    assert output.getvalue() == (
        "[路由] 自动 → skill:knowledge-graph-extraction · confidence=0.98"
        " · tools=read_file,write_file,edit_file,bash\n"
        "完成\n"
    )


def test_stream_chat_prints_thinking_when_enabled(monkeypatch) -> None:
    source = FakeEventSource(
        [
            FakeEvent({"type": "thinking_delta", "content": "先分析"}),
            FakeEvent({"type": "thinking_delta", "content": "问题"}),
            FakeEvent({"type": "delta", "content": "最终"}),
            FakeEvent({"type": "delta", "content": "回答"}),
            FakeEvent({"type": "done"}),
        ]
    )
    request = {}

    def fake_connect_sse(client, method, url, **kwargs):
        request.update(method=method, url=url, **kwargs)
        return source

    monkeypatch.setattr(cli, "connect_sse", fake_connect_sse)
    output = StringIO()

    cli.stream_chat("分析任务", show_thinking=True, output=output)

    assert output.getvalue() == "[思考]\n先分析问题\n\n[回答]\n最终回答\n"
    assert request["json"] == {"message": "分析任务", "thinking": True}


def test_stream_chat_ignores_thinking_by_default(monkeypatch) -> None:
    source = FakeEventSource(
        [
            FakeEvent({"type": "thinking_delta", "content": "内部思考"}),
            FakeEvent({"type": "delta", "content": "回答"}),
            FakeEvent({"type": "done"}),
        ]
    )
    monkeypatch.setattr(cli, "connect_sse", lambda *args, **kwargs: source)
    output = StringIO()

    cli.stream_chat("普通任务", output=output)

    assert output.getvalue() == "回答\n"


def test_stream_chat_prints_tool_calls(monkeypatch) -> None:
    source = FakeEventSource(
        [
            FakeEvent(
                {
                    "type": "tool_start",
                    "tool": "bash",
                    "input": '{"command": "find . -name *.py"}',
                }
            ),
            FakeEvent(
                {
                    "type": "tool_end",
                    "tool": "bash",
                    "output": '{"success": true, "exit_code": 0}',
                }
            ),
            FakeEvent({"type": "done"}),
        ]
    )
    monkeypatch.setattr(cli, "connect_sse", lambda *args, **kwargs: source)
    output = StringIO()

    cli.stream_chat("运行工具", output=output)

    assert output.getvalue() == (
        '[工具调用] bash\n{"command": "find . -name *.py"}\n\n[工具结果] bash\n{"success": true, "exit_code": 0}\n'
    )


def test_stream_chat_prints_model_end_when_thinking_enabled(monkeypatch) -> None:
    source = FakeEventSource(
        [
            FakeEvent({"type": "delta", "content": "准备处理"}),
            FakeEvent(
                {
                    "type": "model_end",
                    "finish_reason": "stop",
                    "tool_calls": 0,
                    "invalid_tool_calls": 0,
                }
            ),
            FakeEvent({"type": "done"}),
        ]
    )
    monkeypatch.setattr(cli, "connect_sse", lambda *args, **kwargs: source)
    output = StringIO()

    cli.stream_chat("诊断", show_thinking=True, output=output)

    assert output.getvalue() == (
        "[回答]\n准备处理\n\n[模型结束] finish_reason=stop tool_calls=0 invalid_tool_calls=0\n"
    )


def test_stream_chat_reports_missing_done(monkeypatch) -> None:
    source = FakeEventSource([FakeEvent({"type": "delta", "content": "部分结果"})])
    monkeypatch.setattr(cli, "connect_sse", lambda *args, **kwargs: source)
    output = StringIO()

    cli.stream_chat("诊断", output=output)

    assert output.getvalue() == "部分结果\n\n[连接异常] SSE 流未收到 done 事件\n"


def test_stream_chat_prints_server_execution_error(monkeypatch) -> None:
    source = FakeEventSource(
        [
            FakeEvent({"type": "delta", "content": "处理中"}),
            FakeEvent(
                {
                    "type": "error",
                    "error": "GraphRecursionError: Recursion limit of 25 reached",
                }
            ),
        ]
    )
    monkeypatch.setattr(cli, "connect_sse", lambda *args, **kwargs: source)
    output = StringIO()

    cli.stream_chat("诊断", output=output)

    assert output.getvalue() == ("处理中\n\n[执行错误]\nGraphRecursionError: Recursion limit of 25 reached\n")


def test_main_forwards_cli_arguments(monkeypatch) -> None:
    received = {}
    monkeypatch.setattr(cli, "stream_chat", lambda message, **kwargs: received.update(message=message, **kwargs))

    cli.main(
        [
            "--url",
            "http://example.test/chat/stream",
            "--agent",
            "data_query",
            "--session-id",
            "session-2",
            "查询销售额",
        ]
    )

    assert received == {
        "message": "查询销售额",
        "url": "http://example.test/chat/stream",
        "agent": "data_query",
        "skill": None,
        "model": None,
        "session_id": "session-2",
        "show_thinking": False,
    }


def test_main_forwards_thinking_flag(monkeypatch) -> None:
    received = {}
    monkeypatch.setattr(cli, "stream_chat", lambda message, **kwargs: received.update(message=message, **kwargs))

    cli.main(["--thinking", "分析任务"])

    assert received["show_thinking"] is True


def test_main_without_message_starts_interactive_mode(monkeypatch) -> None:
    received = {}
    monkeypatch.setattr(cli, "run_interactive", lambda **kwargs: received.update(kwargs))

    cli.main(
        [
            "--url",
            "http://example.test/chat/stream",
            "--model",
            "test:model",
            "--session",
            "session-3",
            "--thinking",
        ]
    )

    assert received == {
        "url": "http://example.test/chat/stream",
        "agent": None,
        "skill": None,
        "model": "test:model",
        "session_id": "session-3",
        "show_thinking": True,
        "first_message": None,
        "no_color": False,
    }


def test_handle_command_switches_model_and_routing_target() -> None:
    state = cli.CLIState(agent="qa")
    output = StringIO()

    assert cli.handle_command("/model deepseek:deepseek-v4-pro", state, output=output)
    assert cli.handle_command("/skill knowledge-graph-extraction", state, output=output)
    assert cli.handle_command("/thinking on", state, output=output)

    assert state.model == "deepseek:deepseek-v4-pro"
    assert state.agent is None
    assert state.skill == "knowledge-graph-extraction"
    assert state.show_thinking is True


def test_handle_command_restores_default_model_and_auto_route() -> None:
    state = cli.CLIState(model="test:model", skill="qa")
    output = StringIO()

    cli.handle_command("/model default", state, output=output)
    cli.handle_command("/auto", state, output=output)

    assert state.model is None
    assert state.agent is None
    assert state.skill is None
    assert "已恢复自动路由" in output.getvalue()


def test_interactive_mode_applies_changed_settings_to_following_messages(monkeypatch) -> None:
    messages = iter(
        [
            "/model deepseek:deepseek-v4-pro",
            "/thinking on",
            "/agent data_query",
            "查询销售额",
            "/skill knowledge-graph-extraction",
            "抽取知识图谱",
            "/exit",
        ]
    )
    calls = []
    output = StringIO()
    monkeypatch.setattr(cli, "stream_chat", lambda message, **kwargs: calls.append((message, kwargs)))

    cli.run_interactive(
        session_id="session-interactive",
        input_func=lambda _prompt: next(messages),
        output=output,
        error=StringIO(),
    )

    assert calls[0] == (
        "查询销售额",
        {
            "url": cli.DEFAULT_STREAM_URL,
            "agent": "data_query",
            "skill": None,
            "model": "deepseek:deepseek-v4-pro",
            "session_id": "session-interactive",
            "show_thinking": True,
            "show_model_info": True,
            "show_routing": True,
            "output": output,
        },
    )
    assert calls[1][0] == "抽取知识图谱"
    assert calls[1][1]["agent"] is None
    assert calls[1][1]["skill"] == "knowledge-graph-extraction"
    assert "再见" in output.getvalue()


def test_interactive_double_slash_sends_literal_slash_message(monkeypatch) -> None:
    messages = iter(["//help", "/exit"])
    calls = []
    monkeypatch.setattr(cli, "stream_chat", lambda message, **kwargs: calls.append(message))

    cli.run_interactive(
        session_id="session-literal",
        input_func=lambda _prompt: next(messages),
        output=StringIO(),
        error=StringIO(),
    )

    assert calls == ["/help"]


def test_interactive_skill_command_can_send_message_inline(monkeypatch) -> None:
    messages = iter(
        [
            "/skill knowledge-graph-extraction 从 ./test_KG/test_medical.txt 抽取知识图谱",
            "/exit",
        ]
    )
    calls = []
    monkeypatch.setattr(
        cli,
        "stream_chat",
        lambda message, **kwargs: calls.append((message, kwargs)),
    )

    cli.run_interactive(
        session_id="session-inline-skill",
        input_func=lambda _prompt: next(messages),
        output=StringIO(),
        error=StringIO(),
    )

    assert calls[0][0] == "从 ./test_KG/test_medical.txt 抽取知识图谱"
    assert calls[0][1]["agent"] is None
    assert calls[0][1]["skill"] == "knowledge-graph-extraction"


def test_whoami_displays_full_provider_and_endpoint() -> None:
    state = cli.CLIState(model="deepseek:deepseek-v4-pro")
    output = StringIO()

    cli.handle_command("/whoami", state, output=output)

    rendered = output.getvalue()
    assert "deepseek:deepseek-v4-pro" in rendered
    assert "DeepSeek (deepseek)" in rendered
    assert "https://api.deepseek.com/" in rendered


def test_prompt_keeps_provider_visible() -> None:
    state = cli.CLIState(model="deepseek:deepseek-v4-pro")

    assert cli._prompt(state, color=False) == "you [deepseek:deepseek-v4-pro] › "


def test_colored_prompt_marks_ansi_sequences_as_zero_width_for_readline() -> None:
    state = cli.CLIState(model="deepseek:deepseek-v4-pro")

    prompt = cli._prompt(state, color=True)

    assert prompt == ("\001\033[1m\033[32m\002you\001\033[0m\002 [deepseek:deepseek-v4-pro] › ")
