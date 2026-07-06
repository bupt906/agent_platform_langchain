from __future__ import annotations

from pydantic import BaseModel


class ChatRequest(BaseModel):
    message: str
    skill: str | None = None
    model: str | None = None
    session_id: str | None = None


class ChatResponse(BaseModel):
    reply: str
    skill_used: str
    model_used: str = ""


class SkillInfoResponse(BaseModel):
    name: str
    description: str
    examples: list[str]
    dependencies: list[str] = []


class SkillListResponse(BaseModel):
    skills: list[SkillInfoResponse]
    total: int


class SubTaskResponse(BaseModel):
    id: str
    skill_name: str
    description: str
    status: str = "pending"
