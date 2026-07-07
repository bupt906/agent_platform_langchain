from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import aiosqlite
import httpx
from fastapi import FastAPI
from langgraph.checkpoint.sqlite import SqliteSaver

from agent_platform.skill_manuals.loader import SkillManualRegistry
from agent_platform.api.middleware import (
    AuthMiddleware,
    ObservabilityMiddleware,
    RateLimitMiddleware,
)
from agent_platform.api.routes import audit, chat, hitl, skills, manuals
from agent_platform.config.settings import settings
from agent_platform.core.deps import PlatformDeps
from agent_platform.core.registry import SkillRegistry
from agent_platform.memory import ConversationSummarizer, SessionStore, UserProfileStore
from agent_platform.models.provider import ModelProvider

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO)
    )

    model_provider = ModelProvider(settings)
    skill_registry = SkillRegistry()
    skill_registry.auto_discover()

    # ── 持久化存储初始化 ──
    memory_db = await aiosqlite.connect(settings.memory_db_path)
    audit_db = await aiosqlite.connect(settings.audit_db_path)

    session_store = SessionStore(memory_db)
    user_profile_store = UserProfileStore(memory_db)
    summarizer = ConversationSummarizer(model_provider)
    checkpointer = SqliteSaver.from_conn_string(settings.memory_db_path)

    from agent_platform.audit.store import AuditStore

    audit_store = AuditStore(audit_db)

    # 审批存储：复用审计数据库连接
    from agent_platform.hitl.store import ApprovalStore

    approval_db = await aiosqlite.connect(settings.audit_db_path)
    approval_store = ApprovalStore(approval_db)

    # ── 技能手册加载 ──
    manuals_dir = settings.skill_manual_path
    if not Path(manuals_dir).is_absolute():
        # 相对路径 → 相对于 agent_platform package 目录解析
        package_dir = Path(__file__).parent.parent  # src/agent_platform/
        manuals_dir = str(package_dir / manuals_dir)
    manual_registry = SkillManualRegistry()
    if settings.skill_manual_enabled:
        manual_registry.load_from_dir(manuals_dir)

    async with httpx.AsyncClient() as http_client:
        deps = PlatformDeps(
            model_provider=model_provider,
            skill_registry=skill_registry,
            http_client=http_client,
            checkpointer=checkpointer,
            session_store=session_store,
            user_profile_store=user_profile_store,
            summarizer=summarizer,
            audit_store=audit_store,
            approval_store=approval_store,
            manual_registry=manual_registry,
        )
        app.state.deps = deps
        app.state.settings = settings

        logger.info(
            "智能体中台启动完成，已注册技能: %s",
            ", ".join(skill_registry.skill_names()),
        )
        yield

    await memory_db.close()
    await audit_db.close()
    await approval_db.close()


app = FastAPI(
    title="智能体中台",
    description="基于 LangChain/LangGraph 的通用智能 Agent 中间件",
    version="0.1.0",
    lifespan=lifespan,
)

# ── 中间件注册（顺序：外→内） ──────────────────────────────

# 1. 可观测性（最外层，统计完整耗时）
app.add_middleware(ObservabilityMiddleware)

# 2. 速率限制
app.add_middleware(RateLimitMiddleware)

# 3. 认证
app.add_middleware(AuthMiddleware)

# ── 路由 ──────────────────────────────────────────────────

app.include_router(chat.router)
app.include_router(skills.router)
app.include_router(audit.router)
app.include_router(hitl.router)
app.include_router(manuals.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
