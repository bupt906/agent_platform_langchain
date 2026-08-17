from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import aiosqlite
import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from agent_platform.api.middleware import (
    AuthMiddleware,
    ObservabilityMiddleware,
    RateLimitMiddleware,
)
from agent_platform.api.routes import artifacts, audit, callback, chat, hitl, preferences, review, skills
from agent_platform.config.settings import settings
from agent_platform.core.deps import PlatformDeps
from agent_platform.core.registry import SkillRegistry
from agent_platform.memory import ConversationSummarizer, SessionStore, UserProfileStore
from agent_platform.models.provider import ModelProvider
from agent_platform.runtime import SkillRuntimeManager
from agent_platform.skills.builder import resolve_skill_tools
from agent_platform.skills.registry import DeclarativeSkillRegistry
from agent_platform.tools import register_all_declarative_tools
from agent_platform.tools.registry import tool_map

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))

    model_provider = ModelProvider(settings)
    skill_registry = SkillRegistry()
    skill_registry.auto_discover()

    # ── 持久化存储初始化 ──
    memory_db = await aiosqlite.connect(settings.memory_db_path)
    await memory_db.execute("PRAGMA journal_mode=WAL")
    audit_db = await aiosqlite.connect(settings.audit_db_path)
    await audit_db.execute("PRAGMA journal_mode=WAL")

    session_store = SessionStore(memory_db)
    user_profile_store = UserProfileStore(memory_db)
    summarizer = ConversationSummarizer(model_provider)
    # AsyncSqliteSaver 复用同一个 memory_db 连接，避免多连接竞争
    checkpointer = AsyncSqliteSaver(memory_db)

    from agent_platform.audit.store import AuditStore

    audit_store = AuditStore(audit_db)

    # 审批存储：复用审计数据库连接
    from agent_platform.hitl.store import ApprovalStore

    approval_db = await aiosqlite.connect(settings.audit_db_path)
    approval_store = ApprovalStore(approval_db)

    # ── 声明式 Skills 加载 ──
    runtime_manager = SkillRuntimeManager(settings)
    expired_artifacts = runtime_manager.artifact_store.cleanup_expired()
    if expired_artifacts:
        logger.info("已清理 %d 个过期或无效 Skill 产物", expired_artifacts)

    async with httpx.AsyncClient(proxy=None) as http_client:
        # ── 知识库后端 ──
        # 必须先于工具注册构造：知识库工具在注册时就要绑定 provider，顺序反了会让
        # 声明式 Skill 在启动校验阶段因「工具未注册」被隔离。
        from agent_platform.knowledge import build_provider

        knowledge = build_provider(http_client, settings)

        register_all_declarative_tools(knowledge=knowledge)
        registered_tools = tool_map()

        def validate_declarative_skill(declarative_skill) -> None:
            runtime_manager.validate_profile(declarative_skill.runtime_profile)
            bound_tools = resolve_skill_tools(declarative_skill, registered_tools)
            logger.info(
                "声明式 Skill '%s' 工具绑定就绪: %s",
                declarative_skill.name,
                ", ".join(tool.name for tool in bound_tools) or "无",
            )

        declarative_registry = DeclarativeSkillRegistry(validator=validate_declarative_skill)
        if declarative_registry.unavailable_skills:
            logger.warning(
                "已隔离 %d 个配置无效的声明式 Skill: %s",
                len(declarative_registry.unavailable_skills),
                ", ".join(declarative_registry.unavailable_skills),
            )
        logger.info("声明式 Skills 加载完成，共 %d 个", declarative_registry.count)

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
            runtime_manager=runtime_manager,
            artifact_store=runtime_manager.artifact_store,
            knowledge=knowledge,
        )
        deps._callback_base = settings.callback_base_url
        app.state.deps = deps
        app.state.settings = settings

        # 注入 document_review 技能依赖（聊天路径的 review_document 工具需要知识库后端）
        from agent_platform.agents.document_review import skill as document_review_skill

        document_review_skill.set_deps(deps)

        logger.info(
            "智能体中台启动完成，已注册agent: %s",
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

# 0. CORS 跨域（最外层，必须在所有中间件之前）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境应限制为前端域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 1. 可观测性（最外层，统计完整耗时）
app.add_middleware(ObservabilityMiddleware)

# 2. 速率限制
app.add_middleware(RateLimitMiddleware)

# 3. 认证
app.add_middleware(AuthMiddleware)

# ── 路由 ──────────────────────────────────────────────────

app.include_router(chat.router)
app.include_router(artifacts.router)
app.include_router(skills.router)
app.include_router(audit.router)
app.include_router(hitl.router)
app.include_router(review.router)
app.include_router(callback.router)
app.include_router(preferences.router)


@app.get("/favicon.ico")
async def favicon():
    """消除浏览器 favicon 请求的 404 日志。"""
    return ""


@app.get("/health")
async def health():
    return {"status": "ok"}
