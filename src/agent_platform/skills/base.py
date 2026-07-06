from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from langgraph.graph.state import CompiledStateGraph

    from agent_platform.models.provider import ModelProvider


@dataclass
class SkillInfo:
    name: str
    description: str
    examples: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)


class BaseSkill(ABC):
    """技能插件基类。

    每个技能封装一个领域 Agent 及其工具集，支持两种运行模式：

    1. **独立模式** — `create_agent()` 返回一个独立的 LangGraph Agent
    2. **组合模式** — `compose()` 将其他技能的子 Agent 作为工具，
       构建一个编排型的父 Agent；返回 None 则自动退化为独立模式

    使用方式：

        # 独立调用
        agent = skill.create_agent(model_provider)

        # 带组合回退（推荐）
        agent = skill.compose(all_skills, model_provider) or skill.create_agent(model_provider)
    """

    # ── 子类必须覆写 ──────────────────────────────────────

    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def description(self) -> str: ...

    @abstractmethod
    def create_agent(self, model_provider: ModelProvider, checkpointer=None) -> CompiledStateGraph:
        """创建独立的 LangGraph Agent（使用 langchain.agents.create_agent）。

        Args:
            model_provider: 模型提供器
            checkpointer: LangGraph checkpointer，用于多轮对话持久化（可选）
        """
        ...

    # ── 可覆写 ────────────────────────────────────────────

    @property
    def examples(self) -> list[str]:
        return []

    @property
    def dependencies(self) -> list[str]:
        return []

    def compose(
        self,
        skills: dict[str, BaseSkill],
        model_provider: ModelProvider,
    ) -> CompiledStateGraph | None:
        """多技能组合编排。

        Args:
            skills: 当前已注册的全部技能 {name: skill_instance}
            model_provider: 模型提供器

        Returns:
            编译后的组合图；返回 None 表示不进行组合，调用方应降级为 create_agent()
        """
        return None

    # ── 元信息 ────────────────────────────────────────────

    @property
    def info(self) -> SkillInfo:
        return SkillInfo(
            name=self.name,
            description=self.description,
            examples=self.examples,
            dependencies=self.dependencies,
        )
