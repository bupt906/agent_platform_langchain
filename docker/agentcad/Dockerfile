FROM python:3.12-slim

ARG AGENTCAD_VERSION=0.4.0

RUN pip install --no-cache-dir "agentcad==${AGENTCAD_VERSION}" \
    && python -c "from agentcad.commands.view import _build_review_payload, _render_single, _resolve_to_glb" \
    && useradd --uid 65532 --no-create-home --shell /usr/sbin/nologin runtime

COPY src/agent_platform/skills/cad-agentcad/scripts/make_viewer.py \
    /opt/agent-platform/make_viewer.py

WORKDIR /workspace
USER runtime
