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
- `tools`：从全局工具池中选，填工具名即可。当前可用：`execute_python`、`bash`、`read_file`、`write_file`
- 正文：就是 Agent 的 system prompt，写清楚工作流程、输出格式、注意事项

### ② assets/ — 示例和模板

Agent 执行时可以读取这些文件，作为输出格式的参考：

```json
// example_schema.json
{
  "entity_types": [{ "name": "设备", "description": "..." }],
  "relationship_types": [{ "name": "has_symptom", "from": "设备", "to": "故障现象" }]
}
```

### ③ references/ — 领域知识注入

`references/` 下的 `.md` 文件会在 Agent 构建时被**自动注入 prompt**（见 `builder.py` 的 `_build_prompt()` 函数）。放：

- 领域规范（如本例的实体抽取规范、Schema 设计指南）
- 输出格式模板
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

以你要开发的"会议纪要" Skill 为例。

### Step 1：判断需要哪些工具

| 需求 | 可用工具 | 够吗 |
|------|---------|------|
| 分析转写文本 | `execute_python`（pandas、re） | ✅ |
| 生成 docx 纪要 | `execute_python`（python-docx） | ✅ |
| 读转写文件 | `read_file` | ✅ |
| 存结果文件 | `write_file` | ✅ |
| 调飞书发消息 | 需要 webhook URL | ❌ → 需要新工具 |

如果 `execute_python` + `bash` + `read_file` + `write_file` 够用，**零代码**，只写 SKILL.md。

如果不够，先写一个 `@tool` 函数（~30 行），在 `tools/__init__.py` 的 `register_all_declarative_tools()` 里注册。

### Step 2：创建目录

```bash
mkdir -p skills/meeting-minutes/references
```

### Step 3：写 SKILL.md

```markdown
---
name: meeting-minutes
description: >-
  从会议转写文本中提取关键信息，生成结构化会议纪要。
  Use when user wants meeting notes, minutes, or action items.
tools: [read_file, execute_python, write_file]
---

# 会议纪要生成

## 工作流程

1. 用 `read_file` 读取转写文本
2. 用 `execute_python` 提取：参会人、议题、决议、待办
3. 用 `execute_python` + `python-docx` 生成 .docx 纪要
4. 用 `write_file` 保存结果

## 生成代码

```python
from docx import Document
doc = Document()
doc.add_heading("会议纪要", level=0)
# ... 按格式填充 ...
doc.save(f"{OUTPUT_DIR}/meeting_minutes.docx")
print("纪要已生成")
```
```

### Step 4：放 references（可选）

```
references/
└── format_guide.md    ← 纪要模板格式规范
```

### Step 5：重启 → 测试

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"skill": "meeting-minutes", "message": "整理这份会议记录.../path/to/transcript.txt"}'
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

## 五、可用工具速查

| 工具名 | 作用 | 调用方式 |
|--------|------|---------|
| `execute_python` | 沙箱执行 Python 代码（pandas/numpy/plotly/docx/openpyxl） | Agent 写 Python 代码 |
| `bash` | 执行受限命令行（不能管道/重定向/串联） | `bash("python scripts/xxx.py")` |
| `read_file` | 读取文件内容（分页支持） | `read_file("path", offset=0, limit=100)` |
| `write_file` | 写文件到沙箱目录 | `write_file("output.txt", "content")` |
| `load_data` | 加载上游 data_key 的数据为 DataFrame | `load_data("sql_abc")` |

### 工具白名单

`execute_python` 沙箱允许的库：`pandas`、`numpy`、`plotly`、`python-docx`、`openpyxl`、`markdown`、`requests`、`pptx` 等。

`bash` 允许的命令：`python`、`ls`、`cat`、`find`、`mkdir`、`cp` 等（禁止 `rm`、`curl` 等危险操作）。

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
