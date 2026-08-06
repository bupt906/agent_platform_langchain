# 一键安装 agentcad（Windows PowerShell）
# 用法：powershell -ExecutionPolicy Bypass -File setup_agentcad.ps1
#
# 自动创建 conda 环境 agentcad-py312 并安装 agentcad 及其依赖。
# agentcad 要求 Python 3.10-3.12（OpenCascade 绑定不支持 3.13+）。

$ErrorActionPreference = "Stop"

Write-Host "=== agentcad 一键安装（Windows） ===" -ForegroundColor Cyan

# 1. 找 conda
$conda = Get-Command conda -ErrorAction SilentlyContinue
if (-not $conda) {
    # 常见 Anaconda/Miniconda 安装路径
    $candidates = @(
        "$env:USERPROFILE\anaconda3\Scripts\conda.exe",
        "$env:USERPROFILE\miniconda3\Scripts\conda.exe",
        "C:\ProgramData\anaconda3\Scripts\conda.exe",
        "C:\ProgramData\miniconda3\Scripts\conda.exe"
    )
    foreach ($c in $candidates) {
        if (Test-Path $c) { $conda = $c; break }
    }
}
if (-not $conda) {
    Write-Host "[错误] 未找到 conda。请先安装 Anaconda 或 Miniconda: https://www.anaconda.com/download" -ForegroundColor Red
    exit 1
}
Write-Host "[ok] 使用 conda: $($conda.Source)"

# 2. 创建 conda 环境（如不存在）
Write-Host "检查 conda 环境 agentcad-py312 ..."
$envExists = & $conda.Source env list 2>&1 | Select-String "agentcad-py312"
if (-not $envExists) {
    Write-Host "创建 conda 环境 agentcad-py312 (Python 3.12) ..."
    & $conda.Source create -y -n agentcad-py312 python=3.12
    if ($LASTEXITCODE -ne 0) { Write-Host "[错误] 创建 conda 环境失败" -ForegroundColor Red; exit 1 }
} else {
    Write-Host "[ok] conda 环境 agentcad-py312 已存在"
}

# 3. 定位 agentcad 环境的 python
$envPython = Join-Path (Split-Path $conda.Source -Parent) "envs\agentcad-py312\python.exe"
if (-not (Test-Path $envPython)) {
    # 备选：conda 命令本身的目录
    $envPython = Join-Path $conda.Source "envs\agentcad-py312\python.exe"
}
if (-not (Test-Path $envPython)) {
    Write-Host "[错误] 无法定位 agentcad-py312 环境的 python.exe" -ForegroundColor Red
    exit 1
}
Write-Host "[ok] agentcad 环境 python: $envPython"

# 4. 安装 agentcad
Write-Host "安装 agentcad 及依赖（首次约需几分钟）..."
& $envPython -m pip install --upgrade pip
& $envPython -m pip install "agentcad>=0.4.0"
if ($LASTEXITCODE -ne 0) { Write-Host "[错误] agentcad 安装失败" -ForegroundColor Red; exit 1 }

# 5. 验证
Write-Host "验证 agentcad ..."
$agentcadExe = Join-Path (Split-Path $envPython -Parent) "agentcad.exe"
if (-not (Test-Path $agentcadExe)) {
    Write-Host "[错误] agentcad.exe 未生成" -ForegroundColor Red
    exit 1
}
& $agentcadExe --help | Out-Null
if ($LASTEXITCODE -ne 0) { Write-Host "[错误] agentcad 无法运行" -ForegroundColor Red; exit 1 }

Write-Host ""
Write-Host "=== 安装完成 ===" -ForegroundColor Green
Write-Host "agentcad 位置: $agentcadExe"
Write-Host ""
Write-Host "启动中台前，确认 bash 白名单含 agentcad（.env 的 BASH_ALLOWED_COMMANDS）。"
Write-Host "SKILL.md 会自动探测 agentcad 路径，无需手动配置。"
