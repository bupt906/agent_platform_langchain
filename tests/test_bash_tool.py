from __future__ import annotations

import json
import shlex
import sys


def _configure(monkeypatch, tmp_path) -> None:
    from agent_platform.config.settings import settings

    monkeypatch.setattr(settings, "bash_allowed_roots", str(tmp_path))
    monkeypatch.setattr(settings, "bash_allowed_commands", "python,python3,pytest,ruff,ls,find")
    monkeypatch.setattr(settings, "bash_default_timeout_seconds", 5)
    monkeypatch.setattr(settings, "bash_max_timeout_seconds", 10)
    monkeypatch.setattr(settings, "bash_max_output_chars", 1_000)


def test_bash_runs_project_python_script(tmp_path, monkeypatch):
    from agent_platform.tools.bash_tool import bash

    _configure(monkeypatch, tmp_path)
    script = tmp_path / "hello.py"
    script.write_text("print('hello from script')", encoding="utf-8")
    command = f"{shlex.quote(sys.executable)} {shlex.quote(str(script))}"

    result = json.loads(
        bash.invoke({"command": command, "working_directory": str(tmp_path)})
    )

    assert result["success"] is True
    assert result["exit_code"] == 0
    assert result["stdout"].strip() == "hello from script"


def test_bash_rejects_working_directory_outside_allowed_roots(tmp_path, monkeypatch):
    from agent_platform.tools.bash_tool import bash

    allowed = tmp_path / "allowed"
    outside = tmp_path / "outside"
    allowed.mkdir()
    outside.mkdir()
    _configure(monkeypatch, allowed)

    result = json.loads(
        bash.invoke(
            {"command": "python missing.py", "working_directory": str(outside)}
        )
    )

    assert result["success"] is False
    assert "PermissionError" in result["error"]


def test_bash_rejects_argument_path_outside_allowed_roots(tmp_path, monkeypatch):
    from agent_platform.tools.bash_tool import bash

    allowed = tmp_path / "allowed"
    outside = tmp_path / "outside.py"
    allowed.mkdir()
    outside.write_text("print('should not run')", encoding="utf-8")
    _configure(monkeypatch, allowed)

    result = json.loads(
        bash.invoke(
            {
                "command": f"{shlex.quote(sys.executable)} {shlex.quote(str(outside))}",
                "working_directory": str(allowed),
            }
        )
    )

    assert result["success"] is False
    assert "PermissionError" in result["error"]


def test_bash_rejects_shell_operators(tmp_path, monkeypatch):
    from agent_platform.tools.bash_tool import bash

    _configure(monkeypatch, tmp_path)

    result = json.loads(
        bash.invoke(
            {
                "command": "python script.py && python other.py",
                "working_directory": str(tmp_path),
            }
        )
    )

    assert result["success"] is False
    assert "命令串联" in result["error"]


def test_bash_rejects_python_inline_code(tmp_path, monkeypatch):
    from agent_platform.tools.bash_tool import bash

    _configure(monkeypatch, tmp_path)
    result = json.loads(
        bash.invoke(
            {
                "command": 'python -c "print(1)"',
                "working_directory": str(tmp_path),
            }
        )
    )

    assert result["success"] is False
    assert "Python -c" in result["error"]


def test_bash_rejects_command_outside_allowlist(tmp_path, monkeypatch):
    from agent_platform.tools.bash_tool import bash

    _configure(monkeypatch, tmp_path)

    result = json.loads(
        bash.invoke({"command": "git status", "working_directory": str(tmp_path)})
    )

    assert result["success"] is False
    assert "不在白名单" in result["error"]


def test_bash_allows_ls_and_find(tmp_path, monkeypatch):
    from agent_platform.tools.bash_tool import bash

    _configure(monkeypatch, tmp_path)
    (tmp_path / "sample.txt").write_text("sample", encoding="utf-8")

    ls_result = json.loads(
        bash.invoke({"command": "ls -1 .", "working_directory": str(tmp_path)})
    )
    find_result = json.loads(
        bash.invoke(
            {
                "command": "find . -maxdepth 1 -name sample.txt",
                "working_directory": str(tmp_path),
            }
        )
    )

    assert ls_result["success"] is True
    assert "sample.txt" in ls_result["stdout"]
    assert find_result["success"] is True
    assert "sample.txt" in find_result["stdout"]


def test_bash_rejects_dangerous_find_actions(tmp_path, monkeypatch):
    from agent_platform.tools.bash_tool import bash

    _configure(monkeypatch, tmp_path)

    result = json.loads(
        bash.invoke(
            {"command": "find . -delete", "working_directory": str(tmp_path)}
        )
    )

    assert result["success"] is False
    assert "禁止 find 选项" in result["error"]


def test_bash_enforces_timeout(tmp_path, monkeypatch):
    from agent_platform.tools.bash_tool import bash

    _configure(monkeypatch, tmp_path)
    script = tmp_path / "slow.py"
    script.write_text("import time\ntime.sleep(2)", encoding="utf-8")

    result = json.loads(
        bash.invoke(
            {
                "command": f"{shlex.quote(sys.executable)} {shlex.quote(str(script))}",
                "working_directory": str(tmp_path),
                "timeout": 1,
            }
        )
    )

    assert result["success"] is False
    assert result["timed_out"] is True


def test_bash_truncates_large_output(tmp_path, monkeypatch):
    from agent_platform.tools.bash_tool import bash

    _configure(monkeypatch, tmp_path)
    script = tmp_path / "large_output.py"
    script.write_text("print('x' * 2000)", encoding="utf-8")

    result = json.loads(
        bash.invoke(
            {
                "command": f"{shlex.quote(sys.executable)} {shlex.quote(str(script))}",
                "working_directory": str(tmp_path),
            }
        )
    )

    assert result["success"] is True
    assert result["truncated"] is True
    assert "truncated" in result["stdout"]


def test_bash_is_registered():
    from agent_platform.tools import register_all_declarative_tools
    from agent_platform.tools.registry import tool_map

    register_all_declarative_tools()

    assert "bash" in tool_map()


def test_knowledge_graph_skill_resolves_three_tools():
    from agent_platform.skills.registry import DeclarativeSkillRegistry
    from agent_platform.tools import register_all_declarative_tools
    from agent_platform.tools.registry import tool_map

    register_all_declarative_tools()
    skill = DeclarativeSkillRegistry().load("knowledge-graph-extraction")
    resolved = [name for name in skill.tools if name in tool_map()]

    assert skill.tools == ["read_file", "write_file", "bash"]
    assert resolved == ["read_file", "write_file", "bash"]
