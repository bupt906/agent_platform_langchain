"""分层 Prompt 构建器。

三层架构：
- 稳定层 (stable)：agent 身份、全局规则 — 缓存在 LRU 中
- 上下文层 (context)：技能描述、可用工具列表 — 技能注册表变更时刷新
- 易变层 (volatile)：用户查询、对话历史 — 每次调用动态构建
"""

from __future__ import annotations

import logging
import time
from functools import lru_cache
from typing import TYPE_CHECKING

from agent_platform.prompts.templates import ROUTER_RULES_STABLE

if TYPE_CHECKING:
    from agent_platform.core.registry import SkillRegistry

logger = logging.getLogger(__name__)


class LayeredPromptBuilder:
    """管理 prompt 三层的构建与缓存。"""

    def __init__(self, cache_ttl: int = 300) -> None:
        self._cache_ttl = cache_ttl
        self._context_cache: dict[int, str] = {}
        self._context_cache_ts: dict[int, float] = {}

    # ── 稳定层 ──────────────────────────────────────────────

    def get_stable_layer(self, skill_name: str = "") -> str:
        """获取指定技能的稳定层 prompt（带 LRU 缓存）。"""
        return _cached_stable_layer(skill_name)

    def get_router_stable(self) -> str:
        """获取路由器的稳定层 prompt。"""
        return ROUTER_RULES_STABLE

    # ── 上下文层 ────────────────────────────────────────────

    def get_context_layer(self, registry: SkillRegistry) -> str:
        """构建上下文层：所有已注册技能的描述。

        结果按 registry 对象 id 缓存，TTL 后失效，确保技能变更后自动刷新。
        """
        reg_id = id(registry)
        now = time.monotonic()

        if reg_id in self._context_cache:
            if now - self._context_cache_ts.get(reg_id, 0) < self._cache_ttl:
                return self._context_cache[reg_id]

        skills = registry.list_skills()
        skill_descriptions = []
        for s in skills:
            dep_info = f"  依赖技能: {', '.join(s.dependencies)}" if s.dependencies else ""
            examples = "\n".join(f"    - {e}" for e in s.examples)
            skill_descriptions.append(
                f"- **{s.name}**: {s.description}\n  示例问题:\n{examples}\n{dep_info}"
            )
        skills_text = "\n".join(skill_descriptions)

        result = f"## 可用技能\n{skills_text}"
        self._context_cache[reg_id] = result
        self._context_cache_ts[reg_id] = now
        return result

    # ── 易变层 ──────────────────────────────────────────────

    def build_volatile(self, query: str, history: list | None = None) -> str:
        """构建易变层：当前查询 + 可选对话历史。"""
        parts = []
        if history:
            history_text = "\n".join(
                f"[{h.get('role', 'unknown')}]: {h.get('content', '')[:300]}"
                for h in history[-5:]  # 最近 5 条
            )
            parts.append(f"## 对话历史\n{history_text}")
        parts.append(f"## 用户问题\n{query}")
        return "\n\n".join(parts)

    # ── 组装 ────────────────────────────────────────────────

    def build_router_prompt(self, registry: SkillRegistry) -> str:
        """组装路由器的完整 system prompt。"""
        stable = self.get_router_stable()
        context = self.get_context_layer(registry)
        return f"{stable}\n\n{context}"

    def build_skill_prompt(self, skill_name: str, query: str, registry: SkillRegistry | None = None) -> str:
        """组装技能的完整 system prompt（稳定层 + 可选的上下文层）。"""
        stable = self.get_stable_layer(skill_name)
        parts = [stable]
        if registry:
            context = self.get_context_layer(registry)
            parts.append(context)
        return "\n\n".join(parts)


@lru_cache(maxsize=32)
def _cached_stable_layer(skill_name: str) -> str:
    """LRU 缓存的稳定层获取（基于技能名）。"""
    # 技能名对应的默认稳定层
    defaults: dict[str, str] = {
        "document_review": "你是 AI 文档审阅专家，专门审查矿山行业文档的合规性、用词规范、技术准确性和场景适配性。",
        "general": "你是一个通用智能助手，尽力回答用户的问题。",
    }
    return defaults.get(skill_name, defaults["general"])
