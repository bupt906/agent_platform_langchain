from agent_platform.tools.budget import ToolBudgetManager
from agent_platform.tools.parallel import execute_tools_parallel, make_parallel_callable
from agent_platform.tools.rate_limiter import ToolRateLimiter
from agent_platform.tools.timeout import with_timeout, wrap_tool_with_timeout
from agent_platform.tools.registry import register, get, get_many, tool_map, all_tools


def register_all_declarative_tools():
    """注册所有 declarative skill 需要的工具。在 app lifespan 中调用。"""
    from agent_platform.tools.python_exec import register_python_tool
    from agent_platform.tools.data_tools import register_data_tools
    from agent_platform.skills.complete import all_complete_tools

    register_python_tool()
    register_data_tools()
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
    "get",
    "get_many",
    "tool_map",
    "all_tools",
    "register_all_declarative_tools",
]
