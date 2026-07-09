# 智能体中台 (Agent Platform) — LangChain 版

基于 **LangChain / LangGraph** 的通用智能 Agent 中间件，提供多模型适配、技能插件机制、LLM 意图路由、多 Agent 编排、SSE 流式输出、MCP Server 集成、持久化记忆、审计日志、Human-in-the-loop 等能力。

---

## 目录

- [项目结构](#项目结构)
- [快速开始](#快速开始)
- [环境变量配置](#环境变量配置)
- [API 接口文档](#api-接口文档)
- [多 Agent 编排模式](#多-agent-编排模式)
- [LLM 意图路由](#llm-意图路由)
- [技能手册系统](#技能手册系统)
- [持久化记忆系统](#持久化记忆系统)
- [审计日志与追踪](#审计日志与追踪)
- [Prompt 分层缓存](#prompt-分层缓存)
- [Tool 优化](#tool-优化)
- [Human-in-the-Loop（人机协同）](#human-in-the-loop人机协同)
- [MCP Server 集成](#mcp-server-集成)
- [配置管理说明](#配置管理说明)
- [添加新技能](#添加新技能)
- [添加组合技能](#添加组合技能)

---

## 项目结构

```
agent_platform_langchain/
├── .env.example                    # 环境变量模板
├── mcp_config.json                 # MCP Server 配置
├── pyproject.toml                  # 项目元数据与依赖
│
├── src/agent_platform/
│   ├── config/
│   │   └── settings.py             # 配置管理
│   │
│   ├── models/
│   │   └── provider.py             # 多模型适配器
│   │
│   ├── memory/                     # 持久化记忆系统
│   │   ├── session_store.py        #   会话持久化 + FTS5 全文搜索
│   │   ├── summarizer.py           #   LLM 驱动的对话摘要
│   │   └── user_profile.py         #   用户画像存储
│   │
│   ├── audit/                      # 审计日志
│   │   ├── schema.py        
│   │   └── store.py                #   审计存储 + 聚合统计
│   │
│   ├── prompts/                    # Prompt 分层缓存
│   │   ├── templates.py            #   可复用模板常量
│   │   └── builder.py             
│   │
│   ├── tools/                      # Tool 优化
│   │   ├── timeout.py              #   工具超时控制
│   │   ├── rate_limiter.py         #   令牌桶速率限制
│   │   ├── budget.py               #   工具调用预算管理
│   │   └── parallel.py             #   并行工具执行
│   │
│   ├── hitl/                       # Human-in-the-Loop
│   │   ├── types.py                
│   │   ├── store.py                #   审批请求持久化
│   │   └── events.py               #   HITL SSE 事件
│   │
│   ├── agents/                     # Agent 插件目录（自动发现）
│   │   ├── base.py                 # Agent 基类 BaseSkill
│   │   ├── qa/                     # 问答 Agent
│   │   ├── data_query/             # 问数 Agent
│   │   ├── contract_review/        # 合同审查 Agent
│   │   ├── composite/              # 组合 Agent
│   │   └── document_review/        # AI 文档审阅 Agent
│   ├── knowledge_bases/            # 知识库目录（向量 RAG）
│   │   ├── registry.py             #   KnowledgeBaseRegistry
│   │   ├── vector_store.py         #   sqlite-vec 向量存储
│   │   ├── compliance.md           #   合规性知识库
│   │   ├── terminology.md          #   用词规范知识库
│   │   ├── technical.md            #   专业技术知识库
│   │   └── mining.md               #   矿山适配知识库
│   │
│   ├── skill_manuals/              # 技能手册目录（操作指南型）
│   │   ├── loader.py                #   手册加载 / 解析 / 关键词匹配
│   │   ├── ppt.md                   #   PowerPoint 操作手册
│   │   ├── feishu.md                #   飞书操作手册
│   │   └── pdf.md                   #   PDF 操作手册
│   │
│   ├── core/
│   │   ├── deps.py                 # 全局依赖容器
│   │   ├── registry.py             # 技能注册中心
│   │   └── router.py               # LLM 意图路由器
│   │
│   ├── graph/
│   │   ├── events.py               # 编排事件定义（含 HITL 事件）
│   │   ├── patterns.py             # 编排模式
│   │   ├── orchestration.py        # 编排引擎
│   │   └── workflows.py            # 示例工作流（合同审查流水线）
│   │
│   ├── mcp_servers/
│   │   └── registry.py             # MCP Server 加载器（含动态重载）
│   │
│   └── api/
│       ├── app.py                  # FastAPI 应用入口 + lifespan + 中间件注册
│       ├── middleware.py            # 认证 / 限流 / 可观测性中间件
│       ├── schemas.py              # 请求/响应 Pydantic 模型
│       └── routes/                  # 接口
└── tests/                          # 测试
```

---

## 快速开始

### 1. 安装依赖

```bash
# 创建虚拟环境
python3 -m venv .venv
source .venv/bin/activate

# 安装项目（含开发依赖）
pip install -e ".[dev]"
```

### 2. 配置环境变量

```bash
cp .env.example .env
```

编辑 `.env`，至少填入一个模型的 API Key：

```env
DEFAULT_MODEL=deepseek:deepseek-chat
DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxx
```

### 3. 启动服务

```bash
uvicorn agent_platform.api.app:app --reload --host 0.0.0.0 --port 8000
```

启动后访问：
- 交互式文档：http://localhost:8000/docs
- ReDoc 文档：http://localhost:8000/redoc
- 健康检查：http://localhost:8000/health

### 4. 测试对话

```bash
# 同步对话（自动路由）
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "公司的请假制度是什么？"}'

# 指定技能
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "上个月销售额是多少？", "skill": "data_query"}'

# SSE 流式对话
curl -N -X POST http://localhost:8000/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"message": "帮我审查这份合同"}'

# 查看所有技能
curl http://localhost:8000/skills

# 查询审计日志
curl http://localhost:8000/audit

# 查看审计统计
curl http://localhost:8000/audit/stats

# 查看待审批请求（HITL）
curl http://localhost:8000/hitl/approvals
```

---

## 环境变量配置

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `DEFAULT_MODEL` | `deepseek:deepseek-chat` | 默认使用的模型，格式为 `提供商:模型名` |
| `DEEPSEEK_API_KEY` | (空) | DeepSeek API 密钥 |
| `DEEPSEEK_BASE_URL` | `https://api.deepseek.com/v1` | DeepSeek API 地址 |
| `QWEN_API_KEY` | (空) | 通义千问 (DashScope) API 密钥 |
| `QWEN_BASE_URL` | `https://dashscope.aliyuncs.com/compatible-mode/v1` | 通义千问 API 地址 |
| `OPENAI_API_KEY` | (空) | OpenAI API 密钥 |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | OpenAI API 地址 |
| `OLLAMA_BASE_URL` | `http://localhost:11434/v1` | Ollama 本地服务地址 |
| `MCP_CONFIG_PATH` | `mcp_config.json` | MCP Server 配置文件路径 |
| `API_HOST` | `0.0.0.0` | 服务监听地址 |
| `API_PORT` | `8000` | 服务监听端口 |
| `LOG_LEVEL` | `INFO` | 日志级别 (DEBUG/INFO/WARNING/ERROR) |
| `REQUEST_TIMEOUT` | `120` | 模型请求超时秒数 |
| `MAX_RETRIES` | `2` | 模型请求失败重试次数 |
| `API_KEY` | (空) | API 认证密钥，为空则不启用认证 |
| `RATE_LIMIT_PER_MINUTE` | `60` | 每 IP 每分钟最大请求数，0 = 不限 |
| `SKILL_MANUAL_PATH` | `skill_manuals` | 技能手册 .md 文件目录（相对于 `agent_platform` package） |
| `SKILL_MANUAL_ENABLED` | `true` | 是否启用技能手册匹配 |
| `MEMORY_DB_PATH` | `memory.db` | 记忆数据库路径 |
| `MEMORY_RETENTION_DAYS` | `90` | 对话历史保留天数 |
| `AUTO_SUMMARIZE_THRESHOLD` | `10` | 触发自动摘要的轮次阈值 |
| `AUDIT_DB_PATH` | `audit.db` | 审计日志数据库路径 |
| `AUDIT_LOG_RETENTION_DAYS` | `365` | 审计日志保留天数 |
| `PROMPT_CACHE_ENABLED` | `true` | 是否启用分层 Prompt 缓存 |
| `TOOL_TIMEOUT_SECONDS` | `30.0` | 单个工具调用超时秒数 |
| `TOOL_RATE_LIMIT_PER_MINUTE` | `100` | 全局工具调用速率限制 |
| `TOOL_BUDGET_MAX_CALLS` | `50` | 单次对话最大工具调用次数 |
| `EMBEDDING_MODEL` | (空) | embedding 模型，格式 `provider:model`。DeepSeek 不支持 embedding，配此项可切换到 Qwen/OpenAI |
| `EMBEDDING_DIMENSIONS` | `1536` | 向量维度 |
| `KB_VECTOR_TOP_K` | `5` | 向量检索返回条数 |
| `KB_VECTOR_THRESHOLD` | `0.7` | 余弦距离阈值 |
| `HITL_ENABLED` | `true` | 是否启用人机协同 |
| `HITL_APPROVAL_TIMEOUT` | `300` | 审批超时秒数 |

**模型 ID 格式**：`提供商:模型名`，例如：
- `deepseek:deepseek-chat` — DeepSeek 对话模型
- `qwen:qwen-plus` — 通义千问 Plus
- `openai:gpt-4o` — OpenAI GPT-4o
- `ollama:llama3` — 本地 Ollama 模型

---

## API 接口文档

### POST `/chat` — 同步对话

**请求体 (ChatRequest)**：

```json
{
  "message": "用户问题",
  "skill": "qa",                // 可选，指定技能名称；省略则自动路由
  "model": "deepseek:deepseek-chat", // 可选，指定模型；省略使用默认模型
  "session_id": "abc123"        // 可选，会话 ID，用于多轮对话记忆
}
```

**响应体 (ChatResponse)**：

```json
{
  "reply": "Agent 的回答内容",
  "skill_used": "qa",           // 实际使用的技能名称
  "model_used": "",             // 实际使用的模型
  "session_id": "abc123",       // 会话 ID
  "approval_required": false,   // 是否需要人工审批
  "approval_id": null           // 审批请求 ID
}
```

**处理流程**：
1. 如果指定了 `skill`：直接调用对应技能的 Agent
2. 如果未指定：LLM 路由器分析意图 → 选择 single 或 multi 模式 → 执行
3. 如果触及 HITL 敏感操作：暂停执行并返回 `approval_required=true`

---

### POST `/chat/stream` — SSE 流式对话

请求体与 `/chat` 相同。返回 Server-Sent Events 流：

```
event: routing
data: {"type": "routing", "skill": "qa", "mode": "single", "confidence": 0.95}

event: delta
data: {"type": "delta", "content": "根据"}

event: delta
data: {"type": "delta", "content": "知识库"}

event: done
data: {"type": "done", "skill": "qa"}
```

**多 Agent 模式的 SSE 事件**：

```
event: routing
data: {"type": "routing", "skill": "multi_agent", "mode": "multi", "confidence": 0.9}

event: plan
data: {"type": "plan", "mode": "parallel", "subtasks": [...]}

event: step_start
data: {"type": "step_start", "step_id": "s1", "skill_name": "contract_review", "description": "审查合同"}

event: step_done
data: {"type": "step_done", "step_id": "s1", "skill_name": "contract_review", "result_summary": "..."}

event: synthesis_start
data: {"type": "synthesis_start"}

event: synthesis_delta
data: {"type": "synthesis_delta", "content": "综合分析结果..."}

event: done
data: {"type": "done", "skill": "multi_agent"}
```

**HITL 审批事件**：

```
event: approval_needed
data: {"type": "approval_needed", "approval_id": "a1b2c3", "operation": "sql_execution", "skill_name": "data_query", "details": "执行 SQL: SELECT * FROM users"}

event: approval_result
data: {"type": "approval_result", "approval_id": "a1b2c3", "status": "approved"}
```

---

### GET `/skills` — 列出所有技能（单agent）

**响应示例**：

```json
{
  "skills": [
    {
      "name": "qa",
      "description": "通用知识问答，基于 RAG 检索知识库回答用户问题",
      "examples": ["公司的请假制度是什么？", "项目的技术架构是怎样的？"],
      "dependencies": []
    },
    {
      "name": "data_contract_review",
      "description": "结合数据查询和合同审查...",
      "examples": ["帮我审查这份采购合同，并验证金额是否与系统数据一致"],
      "dependencies": ["data_query", "contract_review"]
    }
  ],
  "total": 4
}
```

### 技能手册 API

| 端点 | 方法 | 说明 |
|------|------|------|
| `/skill-manuals` | `GET` | 列出所有已加载的操作手册 |
| `/skill-manuals/{name}` | `GET` | 查看指定手册完整内容 |
| `/skill-manuals/{name}` | `PUT` | 动态注册 / 更新手册（无需重启） |
| `/skill-manuals/{name}` | `DELETE` | 删除手册 |
| `/skill-manuals/reload` | `POST` | 从磁盘目录重新加载所有手册 |

**`GET /skill-manuals` 响应示例**：

```json
{
  "manuals": [
    {"name": "ppt", "description": "PowerPoint 操作指南", "keywords": ["PPT", "PowerPoint", "幻灯片"]},
    {"name": "feishu", "description": "飞书操作指南", "keywords": ["飞书", "Feishu", "消息", "通知"]},
    {"name": "pdf", "description": "PDF 操作指南", "keywords": ["PDF", "导出", "打印"]}
  ],
  "total": 3
}
```

**`PUT /skill-manuals/xxx` 请求体**：

```json
{
  "name": "excel",
  "description": "Excel 操作指南",
  "keywords": ["Excel", "表格", "CSV", "xlsx"],
  "content": "# Excel 操作指南\n\n## 读写 Excel\n使用 openpyxl 库：\n```python\nfrom openpyxl import Workbook\n...\n```"
}
```

### GET `/health` — 健康检查

```json
{"status": "ok"}
```

### GET `/audit` — 查询审计日志

**查询参数**：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `session_id` | (空) | 按会话 ID 过滤 |
| `skill` | (空) | 按技能名过滤 |
| `limit` | 100 | 返回条数上限 |
| `offset` | 0 | 分页偏移 |

### GET `/audit/stats` — 审计统计

```json
{
  "total_calls": 1523,
  "total_tokens": 450000,
  "total_duration_ms": 120000.5,
  "avg_duration_ms": 78.8,
  "by_skill": {"qa": 800, "data_query": 500, "contract_review": 223},
  "errors": 12
}
```

### GET `/audit/{id}/tools` — 查询某次调用的工具链

### GET `/hitl/approvals` — 列出待审批请求

### POST `/hitl/approvals/{id}/decide` — 批准/拒绝审批

```json
{
  "decision": "approve",
  "message": "已确认，继续执行"
}
```

### POST `/hitl/replan` — 提交重规划请求

### POST `/review` — 文档审阅

```json
{
  "file_path": "/path/to/document.docx",
  "kb_ids": ["compliance", "terminology"]
}
```

逐句审阅文档，在指定知识库中检索比对，返回每句的审查结论。支持 txt / md / docx 格式。

### GET `/review/kbs` — 列出可用的审查知识库

### 认证

配置 `API_KEY` 环境变量后，所有请求（除 `/health`）均需携带 Bearer Token：

```bash
curl -X POST http://localhost:8000/chat \
  -H "Authorization: Bearer your-api-key" \
  -H "Content-Type: application/json" \
  -d '{"message": "你好"}'
```

不传或传错返回 `401 Unauthorized`。

### 速率限制

通过 `RATE_LIMIT_PER_MINUTE` 配置每 IP 每分钟最大请求数（默认 60）。超出限制返回 `429 Too Many Requests`。`/health` 端点不受限流影响。

## 多 Agent 编排模式

当用户问题需要多个技能协同时，路由器会生成 `ExecutionPlan`，编排引擎根据计划选择以下模式之一：

### Sequential（顺序执行）

步骤之间有依赖关系，前序结果作为后续步骤的上下文传入。

```
用户问题 → [步骤1: 查询数据] → [步骤2: 基于数据审查合同] → 最终结果
```

**适用场景**：「先查数据，再用数据辅助审查合同」

### Parallel（并行执行）

多个步骤独立执行，结果汇总后由 LLM 综合生成最终回答。

```
用户问题 → ┬─ [步骤1: 知识检索] ─┐
           └─ [步骤2: 数据查询] ─┘→ [LLM 综合] → 最终结果
```

**适用场景**：「同时检索知识库和查询数据库」

### Orchestrator（动态编排）

LLM 先将问题分解为子任务，再并行执行所有子任务，最后综合结果。

```
用户问题 → [LLM 任务分解] → ┬─ [子任务1] ─┐
                             ├─ [子任务2] ─┤→ [LLM 综合] → 最终结果
                             └─ [子任务3] ─┘
```

**适用场景**：开放式复杂问题，无法预先确定需要哪些技能

### Sequential with HITL（带审批的顺序执行）

对于敏感操作（如 SQL 执行、合同决策），在执行前自动插入审批门控节点：

```
用户问题 → [审批门控: 确认SQL] → [步骤1: 查询数据] → [审批门控: 确认决策] → [步骤2: 审查合同] → 最终结果
```

**适用场景**：需要人工确认的数据查询、合同签署决策等

---

## LLM 意图路由

路由器是一个使用结构化输出的 LLM 调用，输入用户问题，输出 `RouterDecision`：

```python
class RouterDecision(BaseModel):
    skill_name: str          # 目标技能名（"multi_agent" 表示多技能模式，"general" 表示无匹配）
    rewritten_query: str     # 优化改写后的查询（更适合目标技能处理）
    confidence: float        # 置信度 0.0 ~ 1.0
    mode: "single" | "multi" # 执行模式
    execution_plan: ExecutionPlan | None  # 多 Agent 模式的执行计划
```

路由器的系统提示词中包含所有已注册技能的名称、描述、示例问题和依赖关系，使 LLM 能够做出准确的路由判断。

当用户意图不匹配任何 Agent（路由为 `general`）时，路由器会自动检查技能手册匹配——如果命中，则将手册全文注入 system prompt，让 LLM 严格按手册指导执行。

---

## 技能手册系统（skills）

### 概念

技能手册与 Agent 不同：

| 维度 | Agent（`agents/`） | 技能手册（`skill_manuals/`） |
|------|-------------------|---------------------------|
| 本质 | 自主决策的 AI | 操作说明书 |
| 内容 | Python 代码 + LangGraph + 工具 | Markdown 流程 + 命令模板 + 脚本 |
| 行为 | 自动推理、调用工具 | 被载入上下文，指导 LLM 执行 |
| 例子 | `contract_review` 自动审查合同 | "怎么生成 PPT"、"飞书发消息的套路" |

### 路由匹配

```
用户问 "帮我做个PPT"
      ↓
  LLM Router → 无 Agent 匹配 → general
      ↓
  manual_registry.match() → 关键词命中 ppt.md
      ↓
  将手册全文注入 system prompt
      ↓
  LLM 按手册中的 python-pptx 命令生成代码
```

### 接入方式

三种方式，按灵活度排序：

1. **丢文件**（最简单）—— 把 `.md` 手册文件放到 `skill_manuals/` 目录，重启生效
2. **调 API**（动态）—— `PUT /skill-manuals/xxx` 注册，无需重启

---

## 持久化记忆系统

### 架构

采用 SQLite + FTS5 全文搜索的三级记忆存储：

| 层级 | 存储 | 内容 |
|------|------|------|
| 会话历史 | `conversations` 表 + FTS5 | 每轮对话的完整记录，支持全文检索 |
| 对话摘要 | `ConversationSummarizer` | LLM 驱动的自动摘要，超过阈值（默认 10 轮）触发 |
| 用户画像 | `user_profiles` 表 | 用户偏好、上下文信息，跨 session 持久化 |

### 使用

```python
# 会话历史
await deps.session_store.add_turn(session_id, user_msg, reply, skill_used="qa")
history = await deps.session_store.get_session_history(session_id, limit=50)

# 全文搜索
results = await deps.session_store.search("请假制度")

# 用户画像
await deps.user_profile_store.merge_preferences(session_id, {"language": "zh"})
prefs = await deps.user_profile_store.get_profile(session_id)
```

### 配置

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `MEMORY_DB_PATH` | `memory.db` | 记忆数据库文件路径 |
| `MEMORY_RETENTION_DAYS` | `90` | 历史记录保留天数 |
| `AUTO_SUMMARIZE_THRESHOLD` | `10` | 触发自动摘要的对话轮次 |

---

## 审计日志与追踪

### 审计记录

每次 Agent 调用自动生成 `AuditRecord`，记录：

- 会话 ID、技能、模型
- 用户消息与助手回复
- Token 用量（prompt / completion / total）— 自动从 LLM 响应中提取，支持 DeepSeek/OpenAI/Qwen
- 执行耗时
- 路由置信度
- 异常信息

### 工具调用追踪

每次工具调用生成 `ToolCallRecord`，记录：

- 工具名称
- 调用耗时
- 输入参数（JSON）和输出摘要
- 成功/失败状态

### API

```bash
# 查询日志
curl http://localhost:8000/audit?skill=data_query&limit=50

# 聚合统计
curl http://localhost:8000/audit/stats?days=30

# 工具调用链
curl http://localhost:8000/audit/{audit_id}/tools
```

---

## Prompt 分层缓存

### 三层架构

```
┌─────────────────────────────────────┐
│  稳定层 (Stable)                      │  Agent 身份、全局规则
│  LRU 缓存，TTL 300s                  │  示例："你是一个智能问答助手..."
├─────────────────────────────────────┤
│  上下文层 (Context)                    │  技能描述、工具列表
│  技能注册表变更时刷新                    │  示例："可用技能: qa, data_query..."
├─────────────────────────────────────┤
│  易变层 (Volatile)                     │  用户查询、对话历史
│  每次请求动态构建                       │  示例："用户问题: 请假制度..."
└─────────────────────────────────────┘
```

稳定层和上下文层被 Provider 的 Prompt Cache 命中，每次请求仅易变层产生新的 token 开销。

### 配置

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `PROMPT_CACHE_ENABLED` | `true` | 是否启用分层缓存 |
| `PROMPT_CACHE_TTL` | `300` | 稳定层缓存 TTL（秒） |

---

## Tool 优化

### 超时控制

所有工具调用自动包裹 `asyncio.wait_for`，超时后返回可读错误信息而非抛出异常：

```python
from agent_platform.tools import with_timeout

@with_timeout(10.0)
async def search_knowledge(query: str) -> str: ...
```

配置：`TOOL_TIMEOUT_SECONDS`（默认 30 秒）

### 速率限制

基于令牌桶算法的两级限流（全局 + 单工具）：

```python
from agent_platform.tools import ToolRateLimiter

limiter = ToolRateLimiter(global_rate_per_minute=100)
if await limiter.acquire("search_knowledge"):
    result = await search_knowledge(query)
```

配置：`TOOL_RATE_LIMIT_PER_MINUTE`（默认 100）

### 调用预算

按 session 追踪工具调用次数，超出预算后阻止进一步调用：

```python
from agent_platform.tools import ToolBudgetManager

mgr = ToolBudgetManager(max_calls_per_session=50)
if mgr.can_call(session_id):
    mgr.record_call(session_id, "search_knowledge")
```

配置：`TOOL_BUDGET_MAX_CALLS`（默认 50）

### 并行执行

当 Agent 在单个 ReAct 步骤中发出多个工具调用时，自动并行执行：

```python
from agent_platform.tools import execute_tools_parallel

results = await execute_tools_parallel(tool_calls, max_concurrency=5)
```

---

## Human-in-the-Loop（人机协同）

### 工作原理

基于 LangGraph 的 `interrupt()` / `Command` 原语：

1. 编排图中的敏感节点前插入**审批门控节点**
2. 门控节点调用 `interrupt()` 挂起执行
3. 客户端收到 `approval_needed` SSE 事件
4. 人工通过 API 审批（批准/拒绝）
5. 系统使用 `Command(resume=...)` 恢复执行

### 配置

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `HITL_ENABLED` | `true` | 全局启用/禁用 HITL |
| `HITL_APPROVAL_TIMEOUT` | `300` | 审批超时秒数 |
| `HITL_SENSITIVE_SKILLS` | `["data_query", "contract_review"]` | 需要审批的技能列表 |
| `HITL_AUTO_APPROVE_LOW_RISK` | `false` | 是否自动批准低风险操作 |

### API

```bash
# 查看待审批请求
curl http://localhost:8000/hitl/approvals

# 批准
curl -X POST http://localhost:8000/hitl/approvals/{id}/decide \
  -H "Content-Type: application/json" \
  -d '{"decision": "approve", "message": "已确认"}'

# 拒绝
curl -X POST http://localhost:8000/hitl/approvals/{id}/decide \
  -H "Content-Type: application/json" \
  -d '{"decision": "reject", "message": "不允许此操作"}'
```

---

## MCP Server 集成

通过 `mcp_config.json` 配置外部 MCP Server，使用 `langchain-mcp-adapters` 将 MCP 工具转换为 LangChain 工具。

**配置示例**：

```json
{
  "mcpServers": {
    "filesystem": {
      "command": "mcp-server-filesystem",
      "args": ["/allowed/path"],
      "tool_prefix": "fs_",
      "enabled": true
    },
    "database": {
      "url": "http://localhost:3001/sse",
      "tool_prefix": "db_",
      "enabled": false
    }
  }
}
```

| 字段 | 说明 |
|------|------|
| `command` + `args` | Stdio 模式：通过子进程启动 MCP Server |
| `url` | Streamable HTTP 模式：连接远程 MCP Server |
| `tool_prefix` | 工具名前缀，避免跨 Server 工具名冲突 |
| `enabled` | 是否启用该 Server |

### 动态重载

支持运行时动态加载 MCP 工具，带缓存和筛选能力：

```python
from agent_platform.mcp_servers.registry import load_mcp_tools_dynamic, invalidate_mcp_cache

# 动态加载（默认缓存 300 秒）
tools = await load_mcp_tools_dynamic(config_path, tool_filter="fs_", cache_ttl=60)

# 使缓存失效
invalidate_mcp_cache()
```

---

## 添加新技能（agent）

只需 3 个文件，无需修改任何配置——`SkillRegistry.auto_discover()` 会自动扫描并注册。

### 1. 创建目录结构

```
src/agent_platform/agents/my_agent/
├── __init__.py
├── skill.py
└── tools.py
```

### 2. 实现工具函数 (`tools.py`)

### 3. 实现技能类 (`skill.py`)

### 4. 导出 (`__init__.py`)

重启服务后，路由器能自动将相关问题分发到这个技能。

---

## 添加组合技能

组合技能通过 `compose()` 方法编排多个子 Agent，实现跨技能协作