# 智能体中台 — 开发者指南

## 一、项目概述

智能体中台是一个基于 **LangChain / LangGraph** 的 Agent 运行时平台。你的智能体接入后，平台自动提供：路由决策、工具调用、会话记忆、审计日志、人机协同审批、流式输出。

### 智能体的两种形态

| | Python Agent | 声明式 Skill |
|---|---|---|
| **定义方式** | `agents/<name>/skill.py`（Python 类） | `skills/<name>/SKILL.md`（Markdown） |
| **生效** | 写代码 → 重启 | 写 Markdown → 重启 |
| **适用场景** | 需要专用数据库连接、复杂工具链 | 通用 Python 任务、调外部脚本 |
| **例子** | `document_review` | `knowledge-graph-extraction` |

**推荐新智能体优先用声明式 Skill**，只有声明式 Skill 做不到的时候（如需要数据库连接池、调内部服务 API）才写 Python Agent。

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
│   ├── python_exec.py        ← 沙箱化 Python 执行
│   ├── bash_tool.py          ← 受限命令行执行
│   ├── file_tools.py         ← 文件读写
│   ├── data_tools.py         ← 数据加载（load_data）
│   └── registry.py           ← 全局工具注册表
│
├── api/routes/
│   ├── chat.py               ← /chat, /chat/stream（Agent 对话入口）
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
---
# 正文：System Prompt（Agent 角色定义 + 工作流程）
```

**关键点**：
- `name`：英文，短横线分隔，用作 `skill` 参数值
- `description`：一句英文描述，LLM 路由器根据这个判断用户意图是否匹配
- `tools`：从全局工具池中选，填工具名即可。当前可用：`execute_python`、`bash`、`read_file`、`write_file`、`edit_file`
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

Agent 通过 `bash` 工具调用这些脚本：

```
Agent: "我需要把大文档切片" → bash("python scripts/chunk_document.py ...")
Agent: "合并所有切片结果"   → bash("python scripts/assemble_graph.py ...")
Agent: "校验图的质量"       → bash("python scripts/validate_graph.py ...")
```

脚本用法写在 SKILL.md 正文里，Agent 读 prompt 就知道什么时候调用哪个脚本。

---

## 三、开发新 Skill 的步骤

以你要开发的"知识图谱抽取" Skill 为例。

### Step 1：判断需要哪些工具

| 需求 | 可用工具 | 够吗 |
|------|---------|------|
| 读取文件 | `execute_python`（pandas、re） | ❌ → 需要新工具 |
| 书写文件 | `execute_python`（python-docx） | ❌ → 需要新工具 |
| 运行代码 | `execute_python` （部分）| ❌ → 需要新工具 |

如果 `execute_python` + `bash` + `read_file` + `write_file` + `edit_file` 够用，**零代码**，只写 SKILL.md。

如果不够，开发需要的 `@tool`工具，然后在 `tools/__init__.py` 的 `register_all_declarative_tools()` 里注册。构建工具的具体流程见 [五、工具](#五工具)。

### Step 2：创建目录

```bash
mkdir -p skills/knowledge-graph-extraction
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

### TODO

- 统一面向对象的tool开发规则

---

## 六、快速参考

### 新建 Skill 最少需要

```
skills/<name>/SKILL.md    ← 必需
```

### 一个完整的 Skill 可以有

```
skills/<name>/
├── SKILL.md              ← 必需
├── references/*.md       ← 领域知识，自动注入 prompt
├── scripts/*.py          ← 辅助脚本，Agent 通过 bash 调用
└── assets/*              ← 模板文件，Agent 通过 read_file 读取
```

### 开发检查清单

- [ ] SKILL.md 的 `name` 唯一且用英文
- [ ] `description` 清楚地写了"什么时候用这个 Skill"
- [ ] `tools` 声明了所有需要的工具
- [ ] 正文（body）有明确的工作流程
- [ ] `curl` 测试通过：显式指定 `skill` 参数
- [ ] 自动路由测试：不传 `skill`，LLM 能正确匹配
