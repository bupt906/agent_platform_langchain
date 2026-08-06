# agentcad 部署与集成说明

本文档说明如何将 **agentcad**（CAD 设计 CLI 工具）集成到本智能体中台的
**声明式 Skill** 体系中。

## 集成方式概览

| 项 | 值 |
|----|----|
| Skill 名称 | `cad-agentcad` |
| Skill 位置 | `src/agent_platform/skills/cad-agentcad/` |
| 调用方式 | LLM 通过平台的 `bash` 工具调用 `agentcad` CLI |
| 核心原理 | agentcad 所有命令输出 **结构化 JSON 到 stdout**，进度到 stderr。平台 `bash` 工具恰好把 stdout/stderr 分开返回，完美契合 |

这不是"写死一个 Python 工具"式集成，而是 **agentcad 官方推荐的 skill 集成方式**
（其 SKILL.md 同样声明 `allowed-tools: Bash(agentcad:*)`）。

## 零、一键安装（推荐）

仓库自带一键安装脚本，clone 后运行即可自动创建 agentcad 环境：

**Windows（PowerShell）：**
```powershell
powershell -ExecutionPolicy Bypass -File setup_agentcad.ps1
```

**Linux/macOS：**
```bash
bash setup_agentcad.sh
```

脚本会自动：
1. 定位 conda（Anaconda/Miniconda）
2. 创建 `agentcad-py312` 环境（Python 3.12）
3. `pip install agentcad`
4. 验证安装

**skill 的 SKILL.md 会通过 `find_agentcad.py` 自动探测 agentcad 路径**，
无需手动配置路径。

## 一、手动安装 agentcad（可选）

如果不想用一键脚本，也可以手动装：

agentcad 要求 **Python 3.10–3.12**（OpenCascade 绑定不支持 3.13+）。

```bash
# 推荐：独立 conda 环境（避免与中台 Python 3.11+ 冲突）
conda create -n agentcad-py312 python=3.12 -y
conda activate agentcad-py312
pip install agentcad

# 可选：MCP 支持（本集成不需要，但若以后想用 MCP 方式可装）
# pip install "agentcad[mcp]"
```

验证：

```bash
agentcad --help
```

## 二、让中台 bash 工具能找到 agentcad

中台 `bash` 工具用 `shutil.which()` 解析命令名。**注意：bash 工具不经过
shell、不展开环境变量**（`$VAR` 不会生效），也不允许 `cd && ...` 串联。
所以 SKILL.md 使用 **完整路径** 直接调用 agentcad。

### 推荐：使用完整路径

把 agentcad 的可执行文件完整路径填到 SKILL.md 的命令里，例如：

```
# Linux/macOS
/path/to/anaconda3/envs/agentcad-py312/bin/agentcad run ...

# Windows
D:\software\anaconda\anaconda\envs\agentcad-py312\Scripts\agentcad.exe run ...
```

bash 工具的白名单已包含 `agentcad` 和 `agentcad.exe`，完整路径以这两个
结尾都能通过校验。

### 备选：把 agentcad 加入 PATH

如果你希望 SKILL.md 里的 `agentcad` 裸命令可直接用，把 agentcad 所在的
Scripts/bin 目录加入启动中台的 shell 的 PATH：

```bash
export PATH="/path/to/anaconda3/envs/agentcad-py312/bin:$PATH"
```

这样 SKILL.md 里的 `agentcad init` / `agentcad run ...` 直接可用。


## 三、bash 白名单配置

中台 `bash` 工具要求命令在 `BASH_ALLOWED_COMMANDS` 白名单中。
编辑中台的 `.env`：

```env
BASH_ALLOWED_COMMANDS=python,python3,pytest,ruff,ls,find,agentcad
```

> 本仓库的 `.env.example` 已加 `agentcad`。部署时把 `.env` 也同步加上。
> 注意：如果 `BASH_ALLOWED_COMMANDS` 里写的是命令名，用方式 B 的完整路径
> 时，需要把白名单里加上 `agentcad`（命令名匹配），路径才能通过校验。

## 四、【重要】中文 Windows 编码 bug 修复

**症状**：在中文 Windows 上运行 `agentcad run`，STEP 文件已生成，但命令以
`status: error` 失败，报错：

```
UnicodeEncodeError: 'gbk' codec can't encode character ...
  File ".../agentcad/commands/view.py", line 1808, in _render_unified
    Path(out_html_path).write_text(html)
```

**原因**：agentcad 写 `viewer.html` 时用了系统默认编码（中文 Windows = GBK），
HTML 内含非 GBK 字符导致崩溃。**Linux / macOS 不受影响**（默认 UTF-8）。

**验证**：作者已在 `agentcad` v0.4.x（conda py312）上复现并确认：
- STEP / GLB / preview.png 都能正常生成
- 仅 `viewer.html` 写坏（0 字节）
- 整个 run 命令因此返回 error

### 修复方案（Linux 服务器无需处理）

对中文 Windows，给 agentcad 的 Python 环境注入 `sitecustomize.py` 强制 UTF-8：

```bash
# 在 agentcad 的 conda 环境里
AGENTCAD_PY=$(dirname $(dirname $(which agentcad)))  # = /path/to/envs/agentcad-py312
cat > "$AGENTCAD_PY/Lib/site-packages/sitecustomize.py" <<'EOF'
import sys
# 强制 UTF-8，避免中文 Windows 上 GBK 编码导致 agentcad 写 viewer.html 崩溃
if hasattr(sys, "setdefaultencoding") is False:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
EOF
```

验证修复：

```bash
agentcad init --name smoke && cat > smoke.py <<'EOF'
box = Box(10, 20, 5)
show_object(box)
EOF
agentcad run smoke.py --output v1
# 应看到 status: success
```

## 五、Skill 使用示例

用户对话中，中台自动路由到 `cad-agentcad` skill，LLM 依次执行：

1. `agentcad init --name phone-stand`（初始化项目）
2. `write_file` 写入 `model.py`（build123d 脚本，无需 import）
3. `agentcad run model.py --output v1 --dry-run`（先验证指标）
4. `agentcad run model.py --output v1`（正式运行，生成 STEP + preview + viewer）
5. `agentcad measure ...` / `agentcad inspect ...`（测量/检查）
6. `agentcad export ... --export stl,glb`（网格导出）
7. `complete_task` 提交结果

## 六、故障排查

| 现象 | 原因 | 处理 |
|------|------|------|
| `agentcad: command not found` | 不在 PATH | 按第二部分配置 PATH 或完整路径 |
| `命令 'agentcad' 不在白名单中` | `.env` 未加 | 按第三部分配置 |
| `status: error` + GBK 报错 | 中文 Windows 编码 bug | 按第四部分修复 |
| `run` 成功但 `viewer.html` 0 字节 | 同上 | 同上（STEP 不受影响） |

## 参考

- agentcad 仓库：<https://github.com/jdilla1277/agentcad>
- agentcad 官方 skill（本 SKILL.md 参考了其内容）
- 中台声明式 Skill 机制：`src/agent_platform/skills/registry.py` + `builder.py`
