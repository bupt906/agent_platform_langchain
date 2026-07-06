from __future__ import annotations

import importlib
import logging
import pkgutil
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent_platform.skills.base import BaseSkill, SkillInfo

logger = logging.getLogger(__name__)


class SkillRegistry:
    """技能注册中心，支持手动注册与自动发现。"""

    def __init__(self) -> None:
        self._skills: dict[str, BaseSkill] = {}

    def register(self, skill: BaseSkill) -> None:
        self._skills[skill.name] = skill

    def get(self, name: str) -> BaseSkill | None:
        return self._skills.get(name)

    def list_skills(self) -> list[SkillInfo]:
        return [s.info for s in self._skills.values()]

    def skill_names(self) -> list[str]:
        return list(self._skills.keys())

    def get_all_skills(self) -> dict[str, BaseSkill]:
        """返回已注册的全部技能，key 为技能名，value 为技能实例。

        用于 compose() 调用时传入完整技能表。
        """
        return dict(self._skills)

    def auto_discover(self, package_name: str = "agent_platform.skills") -> None:
        package = importlib.import_module(package_name)
        for importer, modname, ispkg in pkgutil.iter_modules(
            package.__path__, package.__name__ + "."
        ):
            if not ispkg:
                continue
            try:
                mod = importlib.import_module(modname)
                skill = getattr(mod, "skill", None)
                if skill is not None:
                    self.register(skill)
                    logger.info("发现技能: %s", skill.name)
            except Exception:
                logger.warning("跳过无法导入的技能模块: %s", modname, exc_info=True)
