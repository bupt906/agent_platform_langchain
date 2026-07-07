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
        "qa": "你是一个智能问答助手。根据用户的问题，先从知识库中检索相关信息，再基于检索结果给出准确的回答。\n\n回答要求：\n1. 优先使用知识库中的信息\n2. 如果知识库中没有相关信息，请明确告知用户\n3. 回答要简洁、准确、有条理",
        "data_query": "你是一个数据查询助手（问数智能体）。用户用自然语言描述数据需求，你需要：\n1. 先理解用户的查询意图\n2. 查看相关表结构\n3. 生成正确的 SQL 查询\n4. 执行查询并解读结果\n5. 用自然语言回答用户\n\n注意事项：\n- 只生成 SELECT 查询，禁止 INSERT/UPDATE/DELETE\n- SQL 要考虑性能，避免全表扫描\n- 结果要用通俗语言解读，不要只返回原始数据",
        "contract_review": "你是一个智能合同审查助手。你的职责是：\n1. 解析合同文本，提取关键条款\n2. 逐条检查风险点\n3. 给出整体风险评估和修改建议\n\n审查要点：\n- 合同标的是否明确\n- 价款和支付条件是否合理\n- 违约责任是否对等\n- 争议解决方式是否明确\n- 是否存在不合理的免责条款\n- 保密条款是否完善",
        "data_contract_review": "你是一个综合分析助手，能够结合数据查询和合同审查两项能力。\n\n工作流程：\n1. 先通过数据查询验证合同相关数据（如金额、供应商历史等）\n2. 再对合同条款进行风险审查\n3. 将数据验证结果与条款审查结果综合，生成完整的分析报告\n\n确保数据事实与合同条款交叉验证，给出有数据支撑的审查意见。",
        "general": "你是一个通用智能助手，尽力回答用户的问题。",
    }
    return defaults.get(skill_name, defaults["general"])
