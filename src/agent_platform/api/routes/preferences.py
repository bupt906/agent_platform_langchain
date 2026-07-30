"""工作台偏好 API。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from agent_platform.api.schemas import PreferencesRequest, PreferencesResponse
from agent_platform.core.deps import PlatformDeps

router = APIRouter(prefix="/preferences", tags=["preferences"])

_PREFERENCE_KEYS = ("theme", "default_model", "api_base_url")


def _get_deps(request: Request) -> PlatformDeps:
    return request.app.state.deps


def _validate_profile_id(profile_id: str) -> str:
    value = profile_id.strip()
    if not value or len(value) > 128:
        raise HTTPException(status_code=400, detail="profile_id 不能为空且长度不能超过 128")
    return value


async def _current_preferences(deps: PlatformDeps, profile_id: str) -> tuple[dict, str | None]:
    if not deps.user_profile_store:
        raise HTTPException(status_code=503, detail="偏好存储服务不可用")
    data = await deps.user_profile_store.get_profile(profile_id)
    prefs = data.get("preferences", {})
    return ({key: prefs.get(key, "light" if key == "theme" else "") for key in _PREFERENCE_KEYS}, data.get("updated_at"))


@router.get("/{profile_id}", response_model=PreferencesResponse)
async def get_preferences(request: Request, profile_id: str) -> PreferencesResponse:
    profile_id = _validate_profile_id(profile_id)
    prefs, updated_at = await _current_preferences(_get_deps(request), profile_id)
    return PreferencesResponse(profile_id=profile_id, updated_at=updated_at, **prefs)


@router.put("/{profile_id}", response_model=PreferencesResponse)
async def update_preferences(
    request: Request, profile_id: str, body: PreferencesRequest
) -> PreferencesResponse:
    profile_id = _validate_profile_id(profile_id)
    deps = _get_deps(request)
    if not deps.user_profile_store:
        raise HTTPException(status_code=503, detail="偏好存储服务不可用")
    await deps.user_profile_store.merge_preferences(profile_id, body.model_dump())
    prefs, updated_at = await _current_preferences(deps, profile_id)
    return PreferencesResponse(profile_id=profile_id, updated_at=updated_at, **prefs)
