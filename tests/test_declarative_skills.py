"""声明式 Skills 系统测试。"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest


# ── 示例 SKILL.md ────────────────────────────────────────────

_KG_SKILL_MD = """---
name: knowledge-graph-extraction
description: Extract a knowledge graph from documents
tools: [read_file, write_file, bash]
complete_tool: complete_task
---

# Knowledge Graph Extraction

Extract entities and relationships from documents."""

_NO_TOOLS_MD = """---
name: text-formatter
description: Simple text formatting
tools: []
complete_tool: complete_task
---

# Text Formatter

Format text as requested."""


# ── Fixture ──────────────────────────────────────────────────


@pytest.fixture
def skills_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        base = Path(tmpdir)
        (base / "kg").mkdir()
        (base / "kg" / "SKILL.md").write_text(_KG_SKILL_MD, encoding="utf-8")
        (base / "formatter").mkdir()
        (base / "formatter" / "SKILL.md").write_text(_NO_TOOLS_MD, encoding="utf-8")
        yield base


# ── 测试 ──────────────────────────────────────────────────────


class TestDeclarativeSkillRegistry:
    def test_load_from_dir(self, skills_dir):
        from agent_platform.skills.registry import DeclarativeSkillRegistry

        reg = DeclarativeSkillRegistry(skills_dir)
        assert reg.count == 2

    def test_get_skill(self, skills_dir):
        from agent_platform.skills.registry import DeclarativeSkillRegistry

        reg = DeclarativeSkillRegistry(skills_dir)
        skill = reg.get("knowledge-graph-extraction")
        assert skill is not None
        assert skill.name == "knowledge-graph-extraction"
        assert "entities" in skill.body
        assert skill.tools == ["read_file", "write_file", "bash"]

    def test_load_skill(self, skills_dir):
        from agent_platform.skills.registry import DeclarativeSkillRegistry

        reg = DeclarativeSkillRegistry(skills_dir)
        skill = reg.load("knowledge-graph-extraction")
        assert "Extract a knowledge graph" in skill.description

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
        assert names == {"knowledge-graph-extraction", "text-formatter"}

    def test_no_tools_skill(self, skills_dir):
        from agent_platform.skills.registry import DeclarativeSkillRegistry

        reg = DeclarativeSkillRegistry(skills_dir)
        skill = reg.get("text-formatter")
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

    def test_rejects_tools_indented_into_description(self, tmp_path):
        from agent_platform.skills.registry import DeclarativeSkillRegistry

        skill_dir = tmp_path / "broken"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            """---
name: broken
description: >-
  Broken skill
  tools: [read_file, bash]
---

# Broken
""",
            encoding="utf-8",
        )

        registry = DeclarativeSkillRegistry(tmp_path)

        assert registry.count == 0
        assert "缺少顶层 'tools' 字段" in registry.unavailable_skills["broken"]
        with pytest.raises(RuntimeError, match="不可用"):
            registry.load("broken")

    def test_validator_isolates_invalid_skill(self, skills_dir):
        from agent_platform.skills.registry import DeclarativeSkillRegistry

        def reject_missing_tools(skill):
            missing = [name for name in skill.tools if name != "read_file"]
            if missing:
                raise RuntimeError(f"工具未注册: {', '.join(missing)}")

        registry = DeclarativeSkillRegistry(skills_dir, validator=reject_missing_tools)

        assert registry.get("knowledge-graph-extraction") is None
        assert registry.get("text-formatter") is not None
        assert registry.count == 1
        assert "knowledge-graph-extraction" in registry.unavailable_skills

    def test_hot_reload_recovers_isolated_skill(self, tmp_path):
        from agent_platform.skills.registry import DeclarativeSkillRegistry

        skill_dir = tmp_path / "dynamic"
        skill_dir.mkdir()
        skill_md = skill_dir / "SKILL.md"
        skill_md.write_text(
            """---
name: dynamic
description: Dynamic skill
tools: [missing_tool]
---

# Dynamic
""",
            encoding="utf-8",
        )

        def reject_missing_tools(skill):
            if skill.tools:
                raise RuntimeError("工具未注册")

        registry = DeclarativeSkillRegistry(tmp_path, validator=reject_missing_tools)
        assert registry.get("dynamic") is None
        assert "dynamic" in registry.unavailable_skills

        skill_md.write_text(
            """---
name: dynamic
description: Dynamic skill
tools: []
---

# Dynamic
""",
            encoding="utf-8",
        )

        assert registry.get("dynamic") is not None
        assert registry.unavailable_skills == {}

    def test_hot_reloads_changed_skill_markdown(self, tmp_path):
        from agent_platform.skills.registry import DeclarativeSkillRegistry

        skill_dir = tmp_path / "dynamic"
        skill_dir.mkdir()
        skill_md = skill_dir / "SKILL.md"
        skill_md.write_text(
            """---
name: dynamic
description: Dynamic skill
tools: []
---

# Dynamic
""",
            encoding="utf-8",
        )
        registry = DeclarativeSkillRegistry(tmp_path)
        assert registry.load("dynamic").tools == []

        skill_md.write_text(
            """---
name: dynamic
description: Dynamic skill with tools
tools: [read_file, bash]
---

# Dynamic
""",
            encoding="utf-8",
        )

        assert registry.load("dynamic").tools == ["read_file", "bash"]


class TestSkillAgentBuilder:
    def test_recursion_limit_covers_tool_call_budget(self):
        from agent_platform.skills.builder import recursion_limit_for_tool_calls

        assert recursion_limit_for_tool_calls(10) == 25
        assert recursion_limit_for_tool_calls(200) == 405

    def test_build_prompt_includes_body(self, skills_dir):
        from agent_platform.skills.registry import DeclarativeSkillRegistry
        from agent_platform.skills.builder import _build_prompt

        reg = DeclarativeSkillRegistry(skills_dir)
        skill = reg.get("knowledge-graph-extraction")
        prompt = _build_prompt(skill, max_tool_calls=10)
        assert "Knowledge Graph Extraction" in prompt
        assert "complete_task" in prompt
        assert "`read_file`" in prompt
        assert str(skill.source_dir) in prompt
        assert "不要把未经验证的假设当作执行结果" in prompt
        assert "应优先复用这些现有内容" in prompt

    def test_max_tool_calls_replaced(self, skills_dir):
        from agent_platform.skills.registry import DeclarativeSkillRegistry
        from agent_platform.skills.builder import _build_prompt

        reg = DeclarativeSkillRegistry(skills_dir)
        skill = reg.get("knowledge-graph-extraction")
        prompt = _build_prompt(skill, max_tool_calls=5)
        assert "complete_task" in prompt

    def test_build_prompt_includes_runtime_model_identity(self, skills_dir):
        from agent_platform.skills.builder import _build_prompt
        from agent_platform.skills.registry import DeclarativeSkillRegistry

        skill = DeclarativeSkillRegistry(skills_dir).get("knowledge-graph-extraction")
        prompt = _build_prompt(
            skill,
            max_tool_calls=5,
            model_identity="权威模型是 DeepSeek deepseek-v4-pro。",
        )

        assert "运行时模型身份" in prompt
        assert "DeepSeek deepseek-v4-pro" in prompt

    def test_build_agent_compiles(self, skills_dir, model_provider):
        """验证 Agent 可以被构建和编译。"""
        from agent_platform.skills.builder import (
            build_skill_agent,
            resolve_skill_tools,
        )
        from agent_platform.skills.registry import DeclarativeSkillRegistry
        from agent_platform.tools import register_all_declarative_tools
        from agent_platform.tools.registry import tool_map

        reg = DeclarativeSkillRegistry(skills_dir)
        skill = reg.get("knowledge-graph-extraction")
        model = model_provider.get_model()
        register_all_declarative_tools()
        tools = resolve_skill_tools(skill, tool_map())

        agent = build_skill_agent(model, skill, tools=tools, max_tool_calls=6)
        assert agent is not None

    def test_build_agent_rejects_missing_declared_tool(
        self,
        skills_dir,
        model_provider,
    ):
        from agent_platform.skills.builder import build_skill_agent
        from agent_platform.skills.registry import DeclarativeSkillRegistry

        skill = DeclarativeSkillRegistry(skills_dir).load("knowledge-graph-extraction")
        model = model_provider.get_model()

        with pytest.raises(RuntimeError, match="没有绑定到 Agent.*read_file"):
            build_skill_agent(model, skill, tools=[], max_tool_calls=6)

    def test_resolve_skill_tools_rejects_missing_complete_tool(self, skills_dir):
        from agent_platform.skills.builder import resolve_skill_tools
        from agent_platform.skills.registry import DeclarativeSkillRegistry

        skill = DeclarativeSkillRegistry(skills_dir).load("text-formatter")
        skill.complete_tool = "missing_complete"

        with pytest.raises(RuntimeError, match="complete_tool 不存在.*missing_complete"):
            resolve_skill_tools(skill, {})


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


# TODO(Zeyu) 1.应该把所有tool的测试都写在这里
# TODO(Zeyu) 2.所有工具的tool.func()应该改成tool.invoke()
class TestFileTools:
    def test_read_relative_text_file(self, tmp_path, monkeypatch):
        import json

        from agent_platform.config.settings import settings
        from agent_platform.tools.file_tools import read_file

        source = tmp_path / "sample.txt"
        source.write_text("泵体振动异常", encoding="utf-8")
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(settings, "file_read_allowed_roots", ".")

        result = json.loads(read_file.func("sample.txt"))

        assert result["success"] is True
        assert result["content"] == "泵体振动异常"
        assert result["truncated"] is False

    def test_read_file_supports_pagination(self, tmp_path, monkeypatch):
        import json

        from agent_platform.config.settings import settings
        from agent_platform.tools.file_tools import read_file

        source = tmp_path / "sample.txt"
        source.write_text("abcdefghij", encoding="utf-8")
        monkeypatch.setattr(settings, "file_read_allowed_roots", str(tmp_path))

        first = json.loads(read_file.func(str(source), offset=0, limit=4))
        second = json.loads(read_file.func(str(source), offset=first["next_offset"], limit=4))

        assert first["content"] == "abcd"
        assert first["truncated"] is True
        assert first["next_offset"] == 4
        assert second["content"] == "efgh"

    def test_read_file_rejects_path_outside_allowed_roots(self, tmp_path, monkeypatch):
        import json

        from agent_platform.config.settings import settings
        from agent_platform.tools.file_tools import read_file

        allowed = tmp_path / "allowed"
        allowed.mkdir()
        outside = tmp_path / "outside.txt"
        outside.write_text("secret", encoding="utf-8")
        monkeypatch.setattr(settings, "file_read_allowed_roots", str(allowed))

        result = json.loads(read_file.func(str(outside)))

        assert result["success"] is False
        assert "PermissionError" in result["error"]

    def test_read_file_rejects_unsupported_type(self, tmp_path, monkeypatch):
        import json

        from agent_platform.config.settings import settings
        from agent_platform.tools.file_tools import read_file

        source = tmp_path / "sample.bin"
        source.write_bytes(b"binary")
        monkeypatch.setattr(settings, "file_read_allowed_roots", str(tmp_path))

        result = json.loads(read_file.func(str(source)))

        assert result["success"] is False
        assert "不支持的文件类型" in result["error"]

    def test_write_file_creates_parent_directories(self, tmp_path, monkeypatch):
        import json

        from agent_platform.config.settings import settings
        from agent_platform.tools.file_tools import write_file

        monkeypatch.setattr(settings, "file_write_allowed_roots", str(tmp_path))
        target = tmp_path / "kg_output" / "graph.json"

        result = json.loads(write_file.func(str(target), '{"nodes": []}'))

        assert result["success"] is True
        assert result["overwritten"] is False
        assert target.read_text(encoding="utf-8") == '{"nodes": []}'

    def test_write_file_requires_explicit_overwrite(self, tmp_path, monkeypatch):
        import json

        from agent_platform.config.settings import settings
        from agent_platform.tools.file_tools import write_file

        target = tmp_path / "graph.json"
        target.write_text("old", encoding="utf-8")
        monkeypatch.setattr(settings, "file_write_allowed_roots", str(tmp_path))

        rejected = json.loads(write_file.func(str(target), "new"))
        written = json.loads(write_file.func(str(target), "new", overwrite=True))

        assert rejected["success"] is False
        assert "FileExistsError" in rejected["error"]
        assert written["success"] is True
        assert written["overwritten"] is True
        assert target.read_text(encoding="utf-8") == "new"

    def test_write_file_rejects_path_outside_allowed_roots(self, tmp_path, monkeypatch):
        import json

        from agent_platform.config.settings import settings
        from agent_platform.tools.file_tools import write_file

        allowed = tmp_path / "allowed"
        allowed.mkdir()
        outside = tmp_path / "outside.txt"
        monkeypatch.setattr(settings, "file_write_allowed_roots", str(allowed))

        result = json.loads(write_file.func(str(outside), "secret"))

        assert result["success"] is False
        assert "PermissionError" in result["error"]
        assert not outside.exists()

    def test_edit_file_replaces_one_exact_match(self, tmp_path, monkeypatch):
        import json

        from agent_platform.config.settings import settings
        from agent_platform.tools.file_tools import edit_file

        target = tmp_path / "notes.txt"
        target.write_text("before\nold value\nafter\n", encoding="utf-8")
        monkeypatch.setattr(settings, "file_read_allowed_roots", str(tmp_path))
        monkeypatch.setattr(settings, "file_write_allowed_roots", str(tmp_path))

        result = json.loads(edit_file.func(str(target), "old value", "new value"))

        assert result["success"] is True
        assert result["occurrences"] == 1
        assert target.read_text(encoding="utf-8") == "before\nnew value\nafter\n"

    def test_edit_file_rejects_ambiguous_match_without_changing_file(self, tmp_path, monkeypatch):
        import json

        from agent_platform.config.settings import settings
        from agent_platform.tools.file_tools import edit_file

        target = tmp_path / "notes.txt"
        original = "same\nsame\n"
        target.write_text(original, encoding="utf-8")
        monkeypatch.setattr(settings, "file_read_allowed_roots", str(tmp_path))
        monkeypatch.setattr(settings, "file_write_allowed_roots", str(tmp_path))

        result = json.loads(edit_file.func(str(target), "same", "changed"))

        assert result["success"] is False
        assert "出现 2 次" in result["error"]
        assert target.read_text(encoding="utf-8") == original

    def test_edit_file_can_replace_all_matches(self, tmp_path, monkeypatch):
        import json

        from agent_platform.config.settings import settings
        from agent_platform.tools.file_tools import edit_file

        target = tmp_path / "notes.txt"
        target.write_text("same\nsame\n", encoding="utf-8")
        monkeypatch.setattr(settings, "file_read_allowed_roots", str(tmp_path))
        monkeypatch.setattr(settings, "file_write_allowed_roots", str(tmp_path))

        result = json.loads(edit_file.func(str(target), "same", "changed", True))

        assert result["success"] is True
        assert result["occurrences"] == 2
        assert target.read_text(encoding="utf-8") == "changed\nchanged\n"

    def test_edit_file_rejects_missing_match_without_changing_file(self, tmp_path, monkeypatch):
        import json

        from agent_platform.config.settings import settings
        from agent_platform.tools.file_tools import edit_file

        target = tmp_path / "notes.txt"
        original = "original\n"
        target.write_text(original, encoding="utf-8")
        monkeypatch.setattr(settings, "file_read_allowed_roots", str(tmp_path))
        monkeypatch.setattr(settings, "file_write_allowed_roots", str(tmp_path))

        result = json.loads(edit_file.func(str(target), "missing", "changed"))

        assert result["success"] is False
        assert "未找到 old_string" in result["error"]
        assert target.read_text(encoding="utf-8") == original

    def test_file_tools_are_registered(self):
        from agent_platform.tools import register_all_declarative_tools
        from agent_platform.tools.registry import tool_map

        register_all_declarative_tools()

        assert "read_file" in tool_map()
        assert "write_file" in tool_map()
        assert "edit_file" in tool_map()


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
