from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import aiosqlite
import httpx
from fastapi import FastAPI
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from agent_platform.skills.registry import DeclarativeSkillRegistry
from agent_platform.tools import register_all_declarative_tools
from agent_platform.api.middleware import (
    AuthMiddleware,
    ObservabilityMiddleware,
    RateLimitMiddleware,
)
from agent_platform.api.routes import audit, chat, hitl, review, skills
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
    # AsyncSqliteSaver 用 aiosqlite 连接，支持异步操作
    _cp_db = await aiosqlite.connect(settings.memory_db_path)
    checkpointer = AsyncSqliteSaver(_cp_db)

    from agent_platform.audit.store import AuditStore

    audit_store = AuditStore(audit_db)

    # 审批存储：复用审计数据库连接
    from agent_platform.hitl.store import ApprovalStore

    approval_db = await aiosqlite.connect(settings.audit_db_path)
    approval_store = ApprovalStore(approval_db)

    # ── 知识库加载（向量 RAG）──
    from agent_platform.knowledge_bases.registry import KnowledgeBaseRegistry

    kb_registry = KnowledgeBaseRegistry(
        db_path=settings.memory_db_path, dimensions=settings.embedding_dimensions
    )
    kb_dir = Path(__file__).parent.parent / "knowledge_bases"
    await kb_registry.load_from_dir(kb_dir, model_provider=model_provider)
    logger.info("知识库加载完成，共 %d 个（已向量化）", kb_registry.count)

    # ── 声明式 Skills 加载 ──
    register_all_declarative_tools()
    declarative_registry = DeclarativeSkillRegistry()
    logger.info("声明式 Skills 加载完成，共 %d 个", declarative_registry.count)

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
            declarative_registry=declarative_registry,
            kb_registry=kb_registry,
        )
        app.state.deps = deps
        app.state.settings = settings

        logger.info(
            "智能体中台启动完成，已注册agent: %s",
            ", ".join(skill_registry.skill_names()),
        )
        yield

    await memory_db.close()
    await audit_db.close()
    await approval_db.close()
    await _cp_db.close()
    kb_registry.vector_store.close()


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
app.include_router(review.router)


@app.get("/favicon.ico")
async def favicon():
    """消除浏览器 favicon 请求的 404 日志。"""
    return ""


@app.get("/health")
async def health():
    return {"status": "ok"}
