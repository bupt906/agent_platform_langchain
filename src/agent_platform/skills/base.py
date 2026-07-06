from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from langgraph.graph.state import CompiledStateGraph  # create_agent() 的返回类型

    from agent_platform.models.provider import ModelProvider


@dataclass
class SkillInfo:
    name: str
    description: str
    examples: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)


class BaseSkill(ABC):
    """技能插件基类。每个技能封装一个领域 Agent 及其工具集。"""

    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def description(self) -> str: ...

    @property
    def examples(self) -> list[str]:
        return []

    @property
    def dependencies(self) -> list[str]:
        return []

    @abstractmethod
    def create_agent(self, model_provider: ModelProvider) -> CompiledStateGraph:
        """创建独立的 LangGraph Agent（使用 langchain.agents.create_agent）。"""
        ...

    def compose(
        self,
        skills: dict[str, BaseSkill],
        model_provider: ModelProvider,
    ) -> CompiledStateGraph | None:
        """多技能组合编排，返回 None 则退化为 create_agent。"""
        return None

    @property
    def info(self) -> SkillInfo:
        return SkillInfo(
            name=self.name,
            description=self.description,
            examples=self.examples,
            dependencies=self.dependencies,
        )
