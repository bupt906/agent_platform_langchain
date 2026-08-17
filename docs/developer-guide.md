# 智能体中台 — 开发者指南

## 一、项目概述

智能体中台是一个基于 **LangChain / LangGraph** 的 Agent 运行时平台。你的智能体接入后，平台自动提供：路由决策、工具调用、会话记忆、审计日志、人机协同审批、流式输出。

### 智能体的两种形态

| | Python Agent | 声明式 Skill |
|---|---|---|
| **定义方式** | `agents/<name>/skill.py`（Python 类） | `skills/<name>/SKILL.md`（Markdown） |
| **生效** | 写代码 → 重启 | `SKILL.md` 变更可热刷新；工具或 Runtime 代码变更需重启 |
| **适用场景** | 需要专用依赖、数据库连接或复杂服务编排 | 以 Prompt 和已注册工具组织的任务流程 |
| **例子** | `document_review` | `knowledge-graph-extraction`、`cad-agentcad` |

**推荐新能力优先用声明式 Skill**，只有声明式 Skill 做不到的时候（如需要数据库连接池、专用生命周期或内部服务依赖）才写 Python Agent。声明式不等于可以直接执行任意代码：模型生成代码必须使用独立 Runtime Profile 和容器 Sandbox。

### 平台架构（你只需要关心这些目录）

```
src/agent_platform/
├── skills/              ← 你的声明式 Skill 放这里
│   └── your-skill/
│       ├── SKILL.md          ← 必需：skill 定义
│       ├── references/       ← 可选：参考文档（注入 prompt）
│       ├── scripts/          ← 可选：辅助 Python 脚本
│       └── assets/           ← 可选：模板文件
│
├── tools/                ← 所有 Skill 共享的工具池
│   ├── python_exec.py        ← 可终止的受限 Python 子进程
│   ├── bash_tool.py          ← 仅用于可信仓库脚本的受限命令执行
│   ├── file_tools.py         ← 文件读写
│   ├── runtime_tools.py      ← Workspace / Sandbox / Artifact 工具
│   ├── data_tools.py         ← 数据加载（load_data）
│   ├── knowledge_tools.py    ← 企业知识库检索与写入
│   └── registry.py           ← 全局工具注册表
│
├── knowledge/            ← 知识库能力：统一接口 + 可切换后端
│   ├── provider.py           ← KnowledgeProvider 抽象接口
│   ├── providers/            ← 万悟平台 / 知识库中台 / 双跑比对
│   └── factory.py            ← 按 KNOWLEDGE_PROVIDER 选择后端
│
├── runtime/              ← 可执行 Skill 的安全基础设施
│   ├── manager.py            ← Runtime Profile 注册与执行上下文
│   ├── workspace.py          ← Skill / 会话隔离工作区
│   ├── sandbox.py            ← 容器执行、命令策略与资源限制
│   └── artifacts.py          ← 产物发布、TTL 与随机 ID
│
├── api/routes/
│   ├── chat.py               ← /chat, /chat/stream（Agent 对话入口）
│   ├── artifacts.py          ← /artifacts/{id}（产物访问）
│   └── review.py             ← /review（文档审阅入口）
│
└── core/
    └── router.py             ← LLM 路由决策
```

---

## 二、知识图谱 Skill 剖析（参考样例）

`skills/knowledge-graph-extraction/` 是当前最完整的声明式 Skill。下面用它来展示怎么开发一个 Skill。

### 目录结构

```
knowledge-graph-extraction/
├── SKILL.md                     # ① Skill 定义
├── assets/
│   └── example_schema.json      # ② 示例输出（供 Agent 参考）
├── references/                  # ③ 领域知识（注入 prompt）
│   ├── entity-extraction.md     #    实体抽取规范
│   ├── relationship-extraction.md # 关系抽取规范
│   ├── schema-design.md         #    Schema 设计指南
│   ├── fault-diagnosis-schema.md#    故障诊断 Schema 模板
│   ├── output-formats.md        #    输出格式说明
│   ├── pdf-parsing.md           #    PDF 解析指南
│   ├── validation.md            #    校验规范
│   └── visualization.md         #    可视化指南
└── scripts/                     # ④ 辅助脚本（Agent 用 bash 工具调用）
    ├── chunk_document.py        #    长文档切片
    ├── build_chunk_manifest.py  #    构建切片清单
    ├── assemble_graph.py        #    合并多切片图
    ├── validate_graph.py        #    逻辑校验
    └── generate_viewer.py       #    生成可视化页面
```

### ① SKILL.md — 核心文件

```yaml
---
name: knowledge-graph-extraction       # 唯一标识，路由用
description: >-                         # 路由描述（LLM 看到这个决定是否匹配）
  Extract a knowledge graph ... Use this whenever ...
tools: [read_file, write_file, bash]   # 声明需要的工具
# runtime: profile-name               # 可选；需要隔离执行时必须声明
---
# 正文：System Prompt（Agent 角色定义 + 工作流程）
```

**关键点**：
- `name`：英文，短横线分隔，用作 `skill` 参数值
- `description`：一句英文描述，LLM 路由器根据这个判断用户意图是否匹配
- `tools`：从全局工具池中选，填工具名即可。常用工具包括 `execute_python`、`bash`、`read_file`、`write_file`、`edit_file`；隔离 Runtime 使用 `workspace_read`、`workspace_write`、`workspace_list`、`sandbox_run`、`publish_artifact`
- `runtime`：可选的服务端 Runtime Profile 名称。凡是需要运行模型生成代码或不可信第三方 CLI 的 Skill 都必须声明
- 正文：Agent关于这个SKILL该做的事

### ② assets/ — 示例和模板

Agent 执行时可以读取这些文件，作为输出格式的参考：

```json
// example_schema.json
{
  "schema_version": "1.0",
  "domain": "general (adapt to the actual corpus before extracting)",
  "_note": "A neutral starting point. Delete types that don't appear in the documents, and add domain-specific ones. Do NOT extract against this verbatim — a schema that doesn't match the corpus produces a graph that doesn't either.",
  "entity_types": [
    { "type": "Person", "description": "A named individual human." }
  ],
  "relationship_types": [
    { "type": "employed_by", "description": "Person works or worked for the organization.", "source_types": ["Person"], "target_types": ["Organization"], "symmetric": false }
  ]
}
```

### ③ references/ — 细节文档/所需知识

`references/` 下的 `.md` 文件会在 Agent 构建时被**自动注入 prompt**（见 `builder.py` 的 `_build_prompt()` 函数）。放：

- 详细的实践内容（如本例的实体抽取规范、Schema 设计指南）
- 常见错误和最佳实践

Agent 执行时这些内容直接在 system prompt 里，不需要再调工具查。

### ④ scripts/ — 辅助脚本

这些脚本属于仓库中经过代码审查的可信代码，Agent 可通过受限 `bash` 工具调用：

```
Agent: "我需要把大文档切片" → bash("python scripts/chunk_document.py ...")
Agent: "合并所有切片结果"   → bash("python scripts/assemble_graph.py ...")
Agent: "校验图的质量"       → bash("python scripts/validate_graph.py ...")
```

脚本用法写在 SKILL.md 正文里，Agent 读 prompt 就知道什么时候调用哪个脚本。

不要让 `write_file` 生成新的 `.py` 后再交给 `bash` 执行：全局文件工具会拒绝创建或编辑 Python 文件。模型动态生成的代码应放入隔离 Workspace，并通过 `sandbox_run` 在对应 Runtime 镜像内执行。

---

## 三、开发新 Skill 的步骤

以你要开发的"知识图谱抽取" Skill 为例。

### Step 1：判断需要哪些工具

| 需求 | 可用工具 | 够吗 |
|------|---------|------|
| 读取文件 | `execute_python`（pandas、re） | ❌ → 需要新工具 |
| 书写文件 | `execute_python`（python-docx） | ❌ → 需要新工具 |
| 运行代码 | `execute_python` （部分）| ❌ → 需要新工具 |
| 查企业知识库 | `search_knowledge` 等五个工具 | ✅ 直接声明即可 |

**要用知识库不需要写任何代码。** 五个工具已注册在全局工具池里：`search_knowledge`
（检索原文证据）、`answer_from_knowledge`（直接作答）、`list_knowledge_bases`（列出知识库）、
`fetch_knowledge_document`（取全文）、`add_to_knowledge_base`（写入）。
在 `SKILL.md` 的 `tools` 里写名字就能用，背后是万悟平台还是知识库中台由配置决定，
你的 Skill 不受影响。详见 [知识库接入指南](知识库接入指南.md)。

如果只需要文本文件、受限数据处理和已审查的仓库脚本，使用现有工具并只写 `SKILL.md` 即可。

如果需要执行模型生成代码或第三方 CLI，不要把命令加入全局 `bash` 白名单；应创建 Runtime Profile。具体流程见 [六、可执行 Skill 与 Runtime Profile](#六可执行-skill-与-runtime-profile)。

如果不够，开发需要的 `@tool`工具，然后在 `tools/__init__.py` 的 `register_all_declarative_tools()` 里注册。构建工具的具体流程见 [五、工具](#五工具)。

### Step 2：创建目录

```bash
mkdir -p src/agent_platform/skills/knowledge-graph-extraction
```

### Step 3：写 SKILL.md 的 YAML frontmatter

```markdown
---
name: knowledge-graph-extraction
description: >-
  Extract a knowledge graph (entities and relationships) ...
tools: [read_file, write_file, bash]
---
```

### Step 4：references/、assets/、scripts/

```text
knowledge-graph-extraction/
├── SKILL.md                 # Required - main skill file
├── references/              # Optional - documentation 
├── assets/                  # Optional - templates, etc.
└── scripts/                 # Optional - executable code
```

### Step 5：重启 → 测试

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"skill": "knowledge-graph-extraction", "message": "抽取path/to/file下的test.txt文件，并保存到/path/to/save目录下"}'
```

如果要改为自动路由（不传 `skill` 参数），确保 `description` 写得足够清晰，LLM 能识别意图。
---

## 四、路由机制

```
用户消息
    ↓
resolve_route() — LLM 分析意图
    ↓
RouterDecision { skill_name, mode }
    ↓
execute_decision()
    ├── skill_name → agents/xxx     → Python Agent 执行
    ├── skill_name → skills/xxx     → 声明式 Skill 执行
    └── skill_name = "general"      → LLM 通用回答
```

LLM 路由器的 prompt 中包含了所有 Agent 和 Skill 的 `name` + `description`，所以你的 `description` 一定要写清楚"什么时候用"。

### 显式指定 vs 自动路由

```bash
# 显式指定（推荐测试时用）
curl ... -d '{"skill": "meeting-minutes", "message": "..."}'

# 自动路由（生产环境，LLM 根据 description 匹配）
curl ... -d '{"message": "帮我整理会议纪要"}'
```

---

## 五、工具

### 开发步骤

#### 1. 定义工具

在 `src/agent_platform/tools/` 新建文件。使用 `@tool` 声明工具，用类型标注定义参数，用 docstring 告诉 Agent 何时调用。

`bash_tool.py` 的结构：

```python
import json
from langchain_core.tools import tool


@tool("bash")
def bash(command: str, working_directory: str = "", timeout: int = 0) -> str:
    """在允许目录中执行一条白名单命令。"""
    try:
        # 校验参数并执行
        return json.dumps({"success": True, "stdout": "..."}, ensure_ascii=False)
    except Exception as exc:
        return json.dumps({"success": False, "error": str(exc)}, ensure_ascii=False)
```

这个 JSON 先返回给 LangChain/LangGraph 的工具执行器，再作为 `ToolMessage` 放回 Agent 的对话上下文。Agent 读取结果后，决定继续调用工具还是向用户输出结论。

工具结果至少包含 `success`；失败时包含 `error`。

#### 2. 限制权限

所有外部输入都要校验。`bash` 工具的做法是：

- 只访问 `bash_allowed_roots` 内的路径。
- 只执行 `bash_allowed_commands` 中的命令。
- 不启动 shell，禁止管道、重定向和命令串联。
- 设置超时和输出长度上限。
- 不向子进程传递密钥类环境变量。

可调整项统一放在 `src/agent_platform/config/settings.py`，不要写死在工具函数中。

这里的 `bash` 只适合调用仓库内已审查、不可由模型改写的辅助脚本。不要通过新增全局命令白名单来接入 CAD、代码生成器或其他会执行模型输入的工具；这类能力必须使用 Runtime Profile。

#### 3. 注册工具

在工具文件中提供注册函数：

```python
def register_bash_tool() -> None:
    from agent_platform.tools.registry import register

    register(bash)
```

再在 `tools/__init__.py` 的 `register_all_declarative_tools()` 中调用它：

```python
from agent_platform.tools.bash_tool import register_bash_tool

register_bash_tool()
```

`@tool` 名称是工具的唯一标识；例如 `@tool("bash")` 注册后的名称是 `bash`。

#### 4. 交给 Skill 使用

在 `SKILL.md` 的 `tools` 中声明工具名：

```yaml
---
name: knowledge-graph-extraction
tools: [read_file, write_file, bash]
---
```

未声明的工具不会交给该 Skill。

#### 5. 命令如何执行

`@tool("bash")` 会根据函数签名和 docstring 生成工具说明：

- 工具名：`bash`。
- `command: str`：必填。
- `working_directory: str`：可选，默认为空。
- `timeout: int`：可选，默认为 `0`。
- docstring：告诉 Agent 每个参数的用途和限制。

`create_agent(model, all_tools)` 会把这份说明提供给模型。模型根据用户任务选择工具并生成结构化调用：

```json
{
  "name": "bash",
  "args": {
    "command": "python scripts/build.py --out output.json",
    "working_directory": "/project",
    "timeout": 30
  },
  "id": "call_abc123",
  "type": "tool_call"
}
```

LangGraph 根据 `name` 找到 `bash` 工具，校验 `args`，然后等价于执行：

```python
bash.invoke({
    "command": "python scripts/build.py --out output.json",
    "working_directory": "/project",
    "timeout": 30,
})
```

`bash()` 收到参数后，按以下步骤执行：

1. `shlex.split()` 把命令字符串拆成参数数组。
2. 检查工作目录、命令白名单和参数路径；不符合规则就返回错误。
3. `shutil.which()` 查找程序的真实路径，例如把 `python` 解析为 `/project/.venv/bin/python`。
4. `subprocess.run()` 让操作系统启动子进程并运行程序。
5. 子进程结束后，收集退出码、标准输出（`stdout`）和错误输出（`stderr`），再以 JSON 返回给 Agent。

真正执行命令的代码是：

```python
completed = subprocess.run(
    args,
    cwd=cwd,
    env=_safe_environment(),
    stdin=subprocess.DEVNULL,
    capture_output=True,
    text=True,
    timeout=effective_timeout,
    check=False,
)
```

主要参数：

- `args`：可执行文件和参数数组。
- `cwd`：子进程的工作目录。
- `env`：过滤后的环境变量。
- `stdin=DEVNULL`：不允许交互式输入。
- `capture_output=True`：捕获输出，不直接打印到服务端。
- `text=True`：把输出按文本处理。
- `timeout`：超过指定时间就终止子进程并返回超时错误。
- `check=False`：退出码非 `0` 时不抛异常，由工具统一组装失败结果。

`args` 示例：

```python
["/project/.venv/bin/python", "scripts/build.py", "--out", "output.json"]
```

`subprocess.run()` 默认为 `shell=False`：它直接执行 `args[0]` 指定的程序，不会把命令交给 Bash/Sh 解析。因此 `|`、`>`、`&&` 等 Shell 语法不可用，工具也会在执行前拒绝它们。

---

## 六、可执行 Skill 与 Runtime Profile

当 Skill 需要运行模型生成代码或不可信第三方 CLI 时，使用以下安全边界：

```text
SKILL.md
  └─ runtime: profile-name
       └─ SkillRuntimeManager（服务端批准的策略）
            ├─ Workspace（按 Skill + session 隔离）
            ├─ Container Sandbox（无网络、只读根文件系统、资源限额）
            └─ Artifact Store（复制发布、随机 ID、TTL）
```

### 1. 注册 Runtime Profile

在 `src/agent_platform/runtime/manager.py` 中注册 Profile，至少明确：

- 固定版本或 digest 的容器镜像。
- 允许的可执行文件和子命令；不要接受任意 shell。
- Workspace 允许写入的扩展名。
- 网络策略、执行超时、CPU、内存和进程数上限。

CAD Profile 是当前参考实现：它只允许有限的 `agentcad` 子命令和镜像内置 viewer helper，默认无网络、只读根文件系统，并且只挂载当前会话的 Workspace。

### 2. 在 SKILL.md 声明运行时工具

```yaml
---
name: executable-example
description: Run an isolated example workflow when ...
tools: [workspace_read, workspace_write, workspace_list, sandbox_run, publish_artifact]
runtime: executable-example
complete_tool: complete_task
---
```

工具职责：

| 工具 | 用途 |
| --- | --- |
| `workspace_write` | 按 Profile 的扩展名策略写入当前隔离工作区 |
| `workspace_read` / `workspace_list` | 读取或列出当前工作区内容，拒绝路径穿越 |
| `sandbox_run` | 在 Profile 指定的容器及命令白名单中执行 |
| `publish_artifact` | 将工作区文件复制到 Artifact Store，返回公开 `artifact_id` |

Skill 的最终回复应报告 Artifact ID，不应暴露 Workspace 或宿主机路径。HTML Artifact 由 `/artifacts/{artifact_id}` 返回，服务端设置 CSP 和 `nosniff`，前端使用受限 iframe 预览。

### 3. 镜像与部署

- Runtime 镜像定义放在 `docker/<runtime>/`。
- 构建时固定顶层依赖版本，并在镜像构建阶段验证依赖的必要 API。
- 多 worker / 多实例环境应将 `SKILL_ARTIFACT_ROOT` 挂载为共享持久卷。
- `GET /skills` 会返回 `ready`、`runtime_profile`、`runtime_backend` 和不可用原因。Runtime 未就绪时显式请求会安全降级，不会改走宿主机。
- CAD 的完整部署方式见 [CAD Skill 隔离运行时部署说明](agentcad-部署说明.md)。

### 4. 安全测试最低要求

可执行 Skill 至少覆盖：路径穿越、禁止扩展名、未批准命令/子命令、超时终止、无 Runtime 降级、Artifact ID 持久解析和 HTML 安全响应头。

---

## 七、快速参考

### 新建 Skill 最少需要

```
skills/<name>/SKILL.md    ← 必需
```

### 一个完整的 Skill 可以有

```
skills/<name>/
├── SKILL.md              ← 必需
├── references/*.md       ← 领域知识，自动注入 prompt
├── scripts/*.py          ← 仅限仓库内已审查的可信辅助脚本
└── assets/*              ← 模板文件，Agent 通过 read_file 读取
```

需要执行模型生成代码时，另外增加：

```text
docker/<runtime>/Dockerfile
src/agent_platform/runtime/manager.py 中的 Runtime Profile
SKILL.md frontmatter 中的 runtime 与 Runtime 工具
```

### 开发检查清单

- [ ] SKILL.md 的 `name` 唯一且用英文
- [ ] `description` 清楚地写了"什么时候用这个 Skill"
- [ ] `tools` 声明了所有需要的工具
- [ ] 用到知识库时，正文说明了「检索失败」与「知识库里没有」要区别对待
- [ ] 模型生成代码或第三方 CLI 使用独立 Runtime Profile，而非全局 `bash`
- [ ] Runtime 镜像固定版本，命令、网络和资源策略采用最小权限
- [ ] 输出通过 `publish_artifact` 发布，不暴露本地路径
- [ ] `/skills` 在 Runtime 可用和不可用时均返回正确 readiness
- [ ] 正文（body）有明确的工作流程
- [ ] `curl` 测试通过：显式指定 `skill` 参数
- [ ] 自动路由测试：不传 `skill`，LLM 能正确匹配
- [ ] `ruff check src tests`、`pytest -q` 和前端构建通过
