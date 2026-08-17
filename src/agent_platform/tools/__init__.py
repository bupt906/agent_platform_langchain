from agent_platform.tools.budget import ToolBudgetManager
from agent_platform.tools.parallel import execute_tools_parallel, make_parallel_callable
from agent_platform.tools.rate_limiter import ToolRateLimiter
from agent_platform.tools.registry import all_tools, get, get_many, register, register_all, tool_map
from agent_platform.tools.timeout import with_timeout, wrap_tool_with_timeout


def register_all_declarative_tools(knowledge=None):
    """注册所有 declarative skill 需要的工具。在 app lifespan 中调用。

    Args:
        knowledge: 知识库后端。传入后 search_knowledge / answer_from_knowledge /
            list_knowledge_bases 会一并注册，任何 Agent 或 Skill 都能按名字绑定。
            必须在本函数调用前构造好——声明式 Skill 的工具绑定是在注册之后立刻校验的。
    """
    from agent_platform.skills.complete import all_complete_tools
    from agent_platform.tools.bash_tool import register_bash_tool
    from agent_platform.tools.data_tools import register_data_tools
    from agent_platform.tools.file_tools import register_file_tools
    from agent_platform.tools.python_exec import register_python_tool
    from agent_platform.tools.runtime_tools import register_runtime_tools

    register_python_tool()
    register_data_tools()
    register_file_tools()
    register_bash_tool()
    register_runtime_tools()
    if knowledge is not None:
        from agent_platform.tools.knowledge_tools import register_knowledge_tools

        register_knowledge_tools(knowledge)
    for tool in all_complete_tools():
        register(tool)


__all__ = [
    "with_timeout",
    "wrap_tool_with_timeout",
    "ToolRateLimiter",
    "ToolBudgetManager",
    "execute_tools_parallel",
    "make_parallel_callable",
    "register",
    "register_all",
    "get",
    "get_many",
    "tool_map",
    "all_tools",
    "register_all_declarative_tools",
]
