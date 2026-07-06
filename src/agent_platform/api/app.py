from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI

from agent_platform.api.routes import chat, skills
from agent_platform.config.settings import settings
from agent_platform.core.deps import PlatformDeps
from agent_platform.core.registry import SkillRegistry
from agent_platform.models.provider import ModelProvider

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))

    model_provider = ModelProvider(settings)
    skill_registry = SkillRegistry()
    skill_registry.auto_discover()

    async with httpx.AsyncClient() as http_client:
        deps = PlatformDeps(
            model_provider=model_provider,
            skill_registry=skill_registry,
            http_client=http_client,
        )
        app.state.deps = deps

        logger.info(
            "智能体中台启动完成，已注册技能: %s",
            ", ".join(skill_registry.skill_names()),
        )
        yield


app = FastAPI(
    title="智能体中台",
    description="基于 LangChain/LangGraph 的通用智能 Agent 中间件",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(chat.router)
app.include_router(skills.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
