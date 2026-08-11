#!/usr/bin/env bash
# 一键安装 agentcad（Linux/macOS）
# 用法：bash setup_agentcad.sh
#
# 自动创建 conda 环境 agentcad-py312 并安装 agentcad 及其依赖。
# agentcad 要求 Python 3.10-3.12（OpenCascade 绑定不支持 3.13+）。

set -euo pipefail

echo "=== agentcad 一键安装（Linux/macOS） ==="

# 1. 找 conda
CONDA_BIN=""
if command -v conda >/dev/null 2>&1; then
    CONDA_BIN="$(command -v conda)"
elif [ -f "$HOME/anaconda3/bin/conda" ]; then
    CONDA_BIN="$HOME/anaconda3/bin/conda"
elif [ -f "$HOME/miniconda3/bin/conda" ]; then
    CONDA_BIN="$HOME/miniconda3/bin/conda"
elif [ -f "/opt/anaconda3/bin/conda" ]; then
    CONDA_BIN="/opt/anaconda3/bin/conda"
fi

if [ -z "$CONDA_BIN" ]; then
    echo "[错误] 未找到 conda。请先安装 Anaconda 或 Miniconda: https://www.anaconda.com/download" >&2
    exit 1
fi
echo "[ok] 使用 conda: $CONDA_BIN"

# 2. 创建 conda 环境（如不存在）
if ! "$CONDA_BIN" env list | grep -q "agentcad-py312"; then
    echo "创建 conda 环境 agentcad-py312 (Python 3.12) ..."
    "$CONDA_BIN" create -y -n agentcad-py312 python=3.12
else
    echo "[ok] conda 环境 agentcad-py312 已存在"
fi

# 3. 定位 agentcad 环境的 python
CONDA_DIR="$(dirname "$(dirname "$CONDA_BIN")")"
ENV_PYTHON="$CONDA_DIR/envs/agentcad-py312/bin/python"
if [ ! -f "$ENV_PYTHON" ]; then
    echo "[错误] 无法定位 agentcad-py312 环境的 python: $ENV_PYTHON" >&2
    exit 1
fi
echo "[ok] agentcad 环境 python: $ENV_PYTHON"

# 4. 安装 agentcad
echo "安装 agentcad 及依赖（首次约需几分钟）..."
"$ENV_PYTHON" -m pip install --upgrade pip
"$ENV_PYTHON" -m pip install "agentcad>=0.4.0"

# 5. 验证
AGENTCAD_BIN="$(dirname "$ENV_PYTHON")/agentcad"
if [ ! -f "$AGENTCAD_BIN" ]; then
    echo "[错误] agentcad 可执行文件未生成" >&2
    exit 1
fi
"$AGENTCAD_BIN" --help >/dev/null

echo ""
echo "=== 安装完成 ==="
echo "agentcad 位置: $AGENTCAD_BIN"
echo ""
echo "启动中台前，确认 bash 白名单含 agentcad（.env 的 BASH_ALLOWED_COMMANDS）。"
echo "SKILL.md 会自动探测 agentcad 路径，无需手动配置。"
