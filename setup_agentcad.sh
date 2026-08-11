#!/usr/bin/env bash
# 构建 CAD Skill 的固定版本隔离运行时。
set -euo pipefail

IMAGE="${CAD_RUNTIME_IMAGE:-agent-platform/agentcad:0.4.0}"
ENGINE="${SKILL_SANDBOX_ENGINE:-docker}"

if ! command -v "$ENGINE" >/dev/null 2>&1; then
    echo "[错误] 未找到容器引擎: $ENGINE" >&2
    exit 1
fi

echo "构建 CAD Skill Runtime: $IMAGE"
"$ENGINE" build \
    --build-arg AGENTCAD_VERSION=0.4.0 \
    --tag "$IMAGE" \
    --file docker/agentcad/Dockerfile \
    .
"$ENGINE" image inspect "$IMAGE" >/dev/null
echo "[完成] CAD Skill Runtime 已就绪: $IMAGE"
