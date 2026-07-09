"""声明式 Skills 系统测试。"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest


# ── 示例 SKILL.md ────────────────────────────────────────────

_PPT_MD = """---
name: ppt
description: PowerPoint 操作
tools: [execute_python]
complete_tool: complete_task
---

# PPT 操作指南

## 创建演示文稿
使用 python-pptx 库。"""

_FEISHU_MD = """---
name: feishu
description: 飞书操作
tools: [execute_python]
complete_tool: complete_task
---

# 飞书操作指南

## 发送消息
使用 Webhook 机器人。"""

_NO_TOOLS_MD = """---
name: calculator
description: 计算器
tools: []
complete_tool: complete_task
---

# 计算器

直接回答问题。"""


# ── Fixture ──────────────────────────────────────────────────

@pytest.fixture
def skills_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        base = Path(tmpdir)
        (base / "ppt").mkdir()
        (base / "ppt" / "SKILL.md").write_text(_PPT_MD, encoding="utf-8")
        (base / "feishu").mkdir()
        (base / "feishu" / "SKILL.md").write_text(_FEISHU_MD, encoding="utf-8")
        (base / "calculator").mkdir()
        (base / "calculator" / "SKILL.md").write_text(_NO_TOOLS_MD, encoding="utf-8")
        yield base


# ── 测试 ──────────────────────────────────────────────────────

class TestDeclarativeSkillRegistry:
    def test_load_from_dir(self, skills_dir):
        from agent_platform.skills.registry import DeclarativeSkillRegistry

        reg = DeclarativeSkillRegistry(skills_dir)
        assert reg.count == 3

    def test_get_skill(self, skills_dir):
        from agent_platform.skills.registry import DeclarativeSkillRegistry

        reg = DeclarativeSkillRegistry(skills_dir)
        skill = reg.get("ppt")
        assert skill is not None
        assert skill.name == "ppt"
        assert "python-pptx" in skill.body
        assert skill.tools == ["execute_python"]
        assert skill.complete_tool == "complete_task"

    def test_load_skill(self, skills_dir):
        from agent_platform.skills.registry import DeclarativeSkillRegistry

        reg = DeclarativeSkillRegistry(skills_dir)
        skill = reg.load("feishu")
        assert skill.description == "飞书操作"

    def test_load_nonexistent_raises(self, skills_dir):
        from agent_platform.skills.registry import DeclarativeSkillRegistry

        reg = DeclarativeSkillRegistry(skills_dir)
        with pytest.raises(ValueError, match="not found"):
            reg.load("nonexistent")

    def test_get_nonexistent(self, skills_dir):
        from agent_platform.skills.registry import DeclarativeSkillRegistry

        reg = DeclarativeSkillRegistry(skills_dir)
        assert reg.get("nonexistent") is None

    def test_list_infos(self, skills_dir):
        from agent_platform.skills.registry import DeclarativeSkillRegistry

        reg = DeclarativeSkillRegistry(skills_dir)
        infos = reg.list_infos()
        names = {i["name"] for i in infos}
        assert names == {"ppt", "feishu", "calculator"}

    def test_no_tools_skill(self, skills_dir):
        from agent_platform.skills.registry import DeclarativeSkillRegistry

        reg = DeclarativeSkillRegistry(skills_dir)
        skill = reg.get("calculator")
        assert skill.tools == []

    def test_empty_dir(self):
        from agent_platform.skills.registry import DeclarativeSkillRegistry

        with tempfile.TemporaryDirectory() as tmpdir:
            reg = DeclarativeSkillRegistry(tmpdir)
            assert reg.count == 0

    def test_dir_without_skill_md(self):
        from agent_platform.skills.registry import DeclarativeSkillRegistry

        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "empty").mkdir()
            reg = DeclarativeSkillRegistry(tmpdir)
            assert reg.count == 0


class TestSkillAgentBuilder:
    def test_build_prompt_includes_body(self, skills_dir):
        from agent_platform.skills.registry import DeclarativeSkillRegistry
        from agent_platform.skills.builder import _build_prompt

        reg = DeclarativeSkillRegistry(skills_dir)
        skill = reg.get("ppt")
        prompt = _build_prompt(skill, max_tool_calls=10)
        assert "PPT 操作指南" in prompt
        assert "complete_task" in prompt

    def test_max_tool_calls_replaced(self, skills_dir):
        from agent_platform.skills.registry import DeclarativeSkillRegistry
        from agent_platform.skills.builder import _build_prompt

        reg = DeclarativeSkillRegistry(skills_dir)
        skill = reg.get("ppt")
        prompt = _build_prompt(skill, max_tool_calls=5)
        assert "complete_task" in prompt

    def test_build_agent_compiles(self, skills_dir, model_provider):
        """验证 Agent 可以被构建和编译。"""
        from agent_platform.skills.registry import DeclarativeSkillRegistry
        from agent_platform.skills.builder import build_skill_agent
        from agent_platform.skills.complete import get_complete_tool

        reg = DeclarativeSkillRegistry(skills_dir)
        skill = reg.get("ppt")
        model = model_provider.get_model()

        agent = build_skill_agent(model, skill, tools=[], max_tool_calls=6)
        assert agent is not None


class TestCompleteTools:
    def test_all_complete_tools_registered(self):
        from agent_platform.skills.complete import all_complete_tools, get_complete_tool

        tools = all_complete_tools()
        assert len(tools) >= 6

        for name in ["complete_task", "complete_sql", "complete_analyze", "complete_visualize"]:
            assert get_complete_tool(name) is not None

    def test_complete_task_output(self):
        from agent_platform.skills.complete import complete_task

        result = complete_task.func(summary="测试完成", detail="详细结果")
        import json
        data = json.loads(result)
        assert data["summary"] == "测试完成"
        assert data["detail"] == "详细结果"


class TestPythonExec:
    def test_simple_code(self):
        from agent_platform.tools.python_exec import execute_python

        result = execute_python.func("print('hello')")
        import json
        data = json.loads(result)
        assert data["success"] is True
        assert "hello" in data["stdout"]

    def test_import_allowed(self):
        from agent_platform.tools.python_exec import execute_python

        result = execute_python.func("import math\nprint(math.pi)")
        import json
        data = json.loads(result)
        assert data["success"] is True

    def test_import_disallowed(self):
        from agent_platform.tools.python_exec import execute_python

        result = execute_python.func("import os\nprint(os.getcwd())")
        import json
        data = json.loads(result)
        assert data["success"] is False

    def test_timeout(self, monkeypatch):
        from agent_platform.tools import python_exec

        # 缩短超时时间使测试快速完成
        monkeypatch.setattr(python_exec, "PYTHON_EXEC_TIMEOUT", 1)

        result = python_exec.execute_python.func("while True: pass")
        import json
        data = json.loads(result)
        assert data["success"] is False
        assert "Timeout" in data.get("error", "")


class TestDataStore:
    def test_save_and_load(self):
        from agent_platform.tools.data_store import save_dataframe, load_dataframe

        sid = "test_session"
        save_dataframe(sid, "sql_abc", [{"name": "Alice"}, {"name": "Bob"}])
        rows = load_dataframe(sid, "sql_abc")
        assert len(rows) == 2
        assert rows[0]["name"] == "Alice"

    def test_session_isolation(self):
        from agent_platform.tools.data_store import save_dataframe, load_dataframe

        save_dataframe("s1", "k1", [{"a": 1}])
        save_dataframe("s2", "k1", [{"a": 2}])
        assert load_dataframe("s1", "k1")[0]["a"] == 1
        assert load_dataframe("s2", "k1")[0]["a"] == 2
