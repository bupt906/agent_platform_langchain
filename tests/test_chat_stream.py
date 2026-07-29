from __future__ import annotations

from langchain_core.messages import AIMessageChunk

from agent_platform.api.routes.chat import (
    _apply_saved_preferences,
    _chunk_deltas,
    _model_end_data,
    _tool_event_data,
)
from agent_platform.api.schemas import ChatRequest


def test_chat_request_disables_thinking_by_default() -> None:
    request = ChatRequest(message="测试")

    assert request.thinking is False


async def test_saved_preferences_fill_missing_model() -> None:
    class ProfileStore:
        async def get_profile(self, profile_id: str):
            assert profile_id == "browser-profile"
            return {
                "preferences": {
                    "default_model": "deepseek:deepseek-chat",
                }
            }

    class Deps:
        user_profile_store = ProfileStore()

    effective = await _apply_saved_preferences(
        ChatRequest(message="测试", profile_id="browser-profile"), Deps()
    )

    assert effective.model == "deepseek:deepseek-chat"


async def test_request_values_override_saved_preferences() -> None:
    class ProfileStore:
        async def get_profile(self, profile_id: str):
            return {"preferences": {"default_model": "deepseek:deepseek-chat"}}

    class Deps:
        user_profile_store = ProfileStore()

    effective = await _apply_saved_preferences(
        ChatRequest(message="测试", profile_id="browser-profile", agent="custom_agent", model="qwen:qwen-plus"), Deps()
    )

    assert effective.agent == "custom_agent"
    assert effective.model == "qwen:qwen-plus"




def test_chunk_deltas_separates_reasoning_and_answer() -> None:
    chunk = AIMessageChunk(
        content="回答",
        additional_kwargs={"reasoning_content": "思考"},
        response_metadata={"model_provider": "deepseek"},
    )

    assert list(_chunk_deltas(chunk)) == [
        ("thinking_delta", "思考"),
        ("delta", "回答"),
    ]


def test_chunk_deltas_skips_empty_blocks() -> None:
    chunk = AIMessageChunk(content="")

    assert list(_chunk_deltas(chunk)) == []


def test_tool_event_data_truncates_large_arguments() -> None:
    tool_event = _tool_event_data(
        {
            "event": "on_tool_start",
            "name": "write_file",
            "data": {"input": {"file_path": "graph.json", "content": "x" * 2_000}},
        }
    )
    assert tool_event is not None, "错误：on_tool_start 应生成工具事件数据"
    event_type, data = tool_event

    assert event_type == "tool_start"
    assert data["tool"] == "write_file"
    assert "2000 chars" in data["input"]
    assert len(data["input"]) < 1_000


def test_tool_event_data_formats_tool_result() -> None:
    tool_event = _tool_event_data(
        {
            "event": "on_tool_end",
            "name": "bash",
            "data": {"output": '{"success": true}'},
        }
    )
    assert tool_event is not None, "on_tool_end 应生成工具事件数据"
    event_type, data = tool_event

    assert event_type == "tool_end"
    assert data == {
        "type": "tool_end",
        "tool": "bash",
        "output": '{"success": true}',
    }


def test_model_end_data_reports_stop_without_tool_calls() -> None:
    output = AIMessageChunk(
        content="准备继续处理",
        response_metadata={"finish_reason": "stop"},
    )

    data = _model_end_data(
        {"event": "on_chat_model_end", "data": {"output": output}}
    )

    assert data == {
        "type": "model_end",
        "finish_reason": "stop",
        "tool_calls": 0,
        "invalid_tool_calls": 0,
    }
