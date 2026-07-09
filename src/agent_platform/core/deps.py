from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import httpx
from langgraph.checkpoint.memory import InMemorySaver

from agent_platform.core.registry import SkillRegistry
from agent_platform.models.provider import ModelProvider

if TYPE_CHECKING:
    from agent_platform.memory.session_store import SessionStore
    from agent_platform.memory.summarizer import ConversationSummarizer
    from agent_platform.memory.user_profile import UserProfileStore
    from agent_platform.audit.store import AuditStore
    from agent_platform.prompts.builder import LayeredPromptBuilder
    from agent_platform.tools.budget import ToolBudgetManager
    from agent_platform.tools.rate_limiter import ToolRateLimiter
    from agent_platform.skills.registry import DeclarativeSkillRegistry
    from agent_platform.hitl.store import ApprovalStore


@dataclass
class PlatformDeps:
    """全局依赖容器，在 FastAPI lifespan 中初始化。"""

    model_provider: ModelProvider
    skill_registry: SkillRegistry
    http_client: httpx.AsyncClient
    checkpointer: Any = field(default_factory=InMemorySaver)

    # ── 持久化记忆 ──
    session_store: SessionStore | None = None
    user_profile_store: UserProfileStore | None = None
    summarizer: ConversationSummarizer | None = None

    # ── 审计日志 ──
    audit_store: AuditStore | None = None

    # ── Prompt 缓存 ──
    prompt_builder: LayeredPromptBuilder | None = None

    # ── Tool 优化 ──
    tool_rate_limiter: ToolRateLimiter | None = None
    tool_budget_manager: ToolBudgetManager | None = None

    # ── 声明式 Skills ──
    declarative_registry: DeclarativeSkillRegistry | None = None

    # ── HITL ──
    approval_store: ApprovalStore | None = None

    # ── 知识库 ──
    kb_registry: KnowledgeBaseRegistry | None = None  # type: ignore[name-defined]
