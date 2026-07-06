# 智能体中台 (Agent Platform) — LangChain 版

基于 **LangChain / LangGraph** 的通用智能 Agent 中间件，提供多模型适配、技能插件机制、LLM 意图路由、多 Agent 编排、SSE 流式输出、MCP Server 集成等能力。

---

## 目录

- [核心技术栈](#核心技术栈)
- [项目结构](#项目结构)
- [快速开始](#快速开始)
- [环境变量配置](#环境变量配置)
- [API 接口文档](#api-接口文档)
- [内置技能详解](#内置技能详解)
- [多 Agent 编排模式](#多-agent-编排模式)
- [LLM 意图路由](#llm-意图路由)
- [MCP Server 集成](#mcp-server-集成)
- [配置管理说明](#配置管理说明)
- [添加新技能](#添加新技能)
- [添加组合技能](#添加组合技能)
- [技术栈映射（与 PydanticAI 版对照）](#技术栈映射与-pydanticai-版对照)
- [测试](#测试)

---

## 核心技术栈

| 层级 | 技术 | 说明 |
|------|------|------|
| Agent 框架 | LangChain 1.x + LangGraph 1.x | Agent 抽象、工具绑定、对话管理 |
| 工具调用 | `@langchain_core.tools.tool` | 将 Python 函数声明为 Agent 可调用的工具 |
| Agent 构建 | `langchain.agents.create_agent` | 预构建的 ReAct（Reasoning + Acting）Agent |
| 编排引擎 | `langgraph.graph.StateGraph` | 基于有限状态机的多 Agent 工作流编排 |
| 结构化输出 | `ChatModel.with_structured_output()` | 让 LLM 输出符合 Pydantic Schema 的结构化数据 |
| 模型容错 | `ChatModel.with_fallbacks()` | 主模型失败时自动切换到备用模型 |
| MCP 集成 | `langchain-mcp-adapters` 0.3+ | 将 MCP Server 的工具转换为 LangChain 工具 |
| Web 框架 | FastAPI 0.115+ | 异步 REST API 框架 |
| 流式输出 | SSE-Starlette 3.x | Server-Sent Events 流式推送 |
| 配置管理 | pydantic-settings 2.x | 从环境变量 / `.env` 文件自动加载配置（详见下方说明） |
| HTTP 客户端 | httpx 0.27+ | 异步 HTTP 请求 |
| 会话管理 | LangGraph Checkpointer (InMemorySaver) | 多轮对话状态持久化 |
| 安全 | Bearer Token + 滑动窗口限流 | API 认证与速率限制 |
| 可观测性 | 请求日志中间件 | 请求耗时统计 |

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
│   │   └── settings.py             # 配置管理（pydantic-settings）
│   │
│   ├── models/
│   │   └── provider.py             # 多模型适配器（DeepSeek/Qwen/Ollama/OpenAI）
│   │
│   ├── skills/                     # 技能插件目录（自动发现）
│   │   ├── base.py                 # 技能基类 BaseSkill
│   │   ├── qa/                     # 知识问答技能 (RAG)
│   │   │   ├── skill.py            #   Agent 定义 + 系统提示词
│   │   │   └── tools.py            #   知识库检索工具
│   │   ├── data_query/             # 自然语言问数技能 (Text-to-SQL)
│   │   │   ├── skill.py            #   Agent 定义 + 系统提示词
│   │   │   └── tools.py            #   SQL 执行 / 表结构查询工具
│   │   ├── contract_review/        # 合同审查技能
│   │   │   ├── skill.py            #   Agent 定义 + 系统提示词
│   │   │   └── tools.py            #   条款解析 / 风险检查 / 评估工具
│   │   └── composite/              # 组合技能（数据 + 合同审查）
│   │       └── skill.py            #   编排多个子 Agent
│   │
│   ├── core/
│   │   ├── deps.py                 # 全局依赖容器 PlatformDeps
│   │   ├── registry.py             # 技能注册中心 SkillRegistry
│   │   └── router.py               # LLM 意图路由器
│   │
│   ├── graph/
│   │   ├── events.py               # 编排事件定义（SSE 推送用）
│   │   ├── patterns.py             # 编排模式（Sequential/Parallel/Orchestrator）
│   │   ├── orchestration.py        # 编排引擎 OrchestrationEngine
│   │   └── workflows.py            # 示例工作流（合同审查流水线）
│   │
│   ├── mcp_servers/
│   │   └── registry.py             # MCP Server 加载器
│   │
│   ├── api/
│       ├── app.py                  # FastAPI 应用入口 + lifespan + 中间件注册
│       ├── middleware.py            # 认证 / 限流 / 可观测性中间件
│       ├── schemas.py              # 请求/响应 Pydantic 模型
│       └── routes/
│           ├── chat.py             # /chat 和 /chat/stream 端点
│           └── skills.py           # /skills 端点
│
└── tests/                          # 测试套件（51 个测试）
    ├── conftest.py                 # Pytest Fixtures
    ├── test_skills.py              # 技能注册 + 工具函数 + SQL 注入校验测试
    ├── test_router.py              # 路由决策 + 路由 prompt 构建 + invoke config 测试
    ├── test_orchestration.py       # 事件序列化 + 执行计划 + sentinel 模式测试
    └── test_multi_agent_router.py  # 多 Agent 模式 + 组合技能 compose 测试
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

编辑 `.env`，至少填入一个模型提供商的 API Key：

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
  "model_used": ""              // 实际使用的模型
}
```

**处理流程**：
1. 如果指定了 `skill`：直接调用对应技能的 Agent
2. 如果未指定：LLM 路由器分析意图 → 选择 single 或 multi 模式 → 执行

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

---

### GET `/skills` — 列出所有技能

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

### GET `/health` — 健康检查

```json
{"status": "ok"}
```

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

---

## 内置技能详解

### qa — 通用知识问答 (RAG)

基于检索增强生成(RAG)模式的知识问答。Agent 先调用知识库检索工具获取相关文档片段，再基于检索结果生成回答。

| 项目 | 说明 |
|------|------|
| 工具 | `search_knowledge(query, top_k)` — 检索知识库 |
| 适用场景 | 企业制度查询、技术文档检索、FAQ 问答 |
| 待接入 | Milvus / Elasticsearch 向量检索引擎 |

### data_query — 自然语言问数 (Text-to-SQL)

将用户的自然语言问题转换为 SQL 查询，执行后用通俗语言解读结果。

| 项目 | 说明 |
|------|------|
| 工具 | `query_table_schema(table_name)` — 查看表结构 |
|      | `run_sql_query(sql)` — 执行 SELECT 查询 |
| 安全机制 | 多层 SQL 校验：注释移除 → 多语句检测 → SELECT 关键字白名单 |
| 内置表 | users, orders, products |
| 待接入 | 真实数据库连接池 |

### contract_review — 智能合同审查

解析合同文本、逐条检查法律风险、给出整体评估和修改建议。

| 项目 | 说明 |
|------|------|
| 工具 | `extract_clauses(contract_text)` — 提取合同条款 |
|      | `review_clause(clause_text)` — 单条款风险审查 |
|      | `overall_risk_assessment(findings)` — 整体风险评估 |
| 审查要点 | 标的明确性、价款合理性、违约对等性、免责条款、保密条款 |
| 待接入 | 法律 NLP 模型 + 法律知识库规则引擎 |

### data_contract_review — 数据驱动合同审查（组合技能）

这是一个**组合技能**，依赖 `data_query` 和 `contract_review` 两个原子技能。它创建一个编排 Agent，内部调用两个子 Agent 的能力：

1. 先通过数据查询验证合同相关数据（金额、供应商历史等）
2. 再对合同条款进行风险审查
3. 将数据验证结果与条款审查结果交叉验证，生成综合报告

---

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

---

## 配置管理说明

本项目使用 **pydantic-settings** 进行配置管理。

### pydantic-settings 是什么？

[pydantic-settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) 是 Pydantic 生态的一个独立库，它扩展了 Pydantic 的 `BaseModel`，提供了一个 `BaseSettings` 基类。核心能力是**自动从多种来源加载配置值**，按以下优先级（从高到低）：

1. **构造函数参数** — 代码中直接传入的值
2. **环境变量** — 系统环境变量（如 `export DEEPSEEK_API_KEY=sk-xxx`）
3. **`.env` 文件** — 项目根目录的 `.env` 文件中的键值对
4. **默认值** — 类定义中的 `default` / `default_factory`

### 它与普通 Pydantic BaseModel 的区别

| 特性 | `BaseModel` | `BaseSettings` |
|------|-------------|----------------|
| 数据来源 | 必须手动传入 | 自动读取环境变量 + `.env` 文件 |
| 类型验证 | 有 | 有（完全相同） |
| 环境变量映射 | 无 | 字段名自动映射为大写环境变量名 |
| `.env` 文件支持 | 无 | 内置支持 |
| 适用场景 | API 请求体、数据模型 | 应用配置、密钥管理 |

### 本项目中的用法

```python
# src/agent_platform/config/settings.py

class ModelConfig(BaseSettings):
    deepseek_api_key: str = ""      # ← 自动读取环境变量 DEEPSEEK_API_KEY
    deepseek_base_url: str = "https://api.deepseek.com/v1"
    # ...

    model_config = {"env_file": ".env", "extra": "ignore"}

class Settings(BaseSettings):
    default_model: str = "deepseek:deepseek-chat"  # ← 自动读取 DEFAULT_MODEL
    api_host: str = "0.0.0.0"                      # ← 自动读取 API_HOST
    api_port: int = 8000                            # ← 自动读取 API_PORT（自动转为 int）
    models: ModelConfig = Field(default_factory=ModelConfig)
    # ...

settings = Settings()  # 实例化时自动加载所有配置
```

**优点**：无需手动写 `os.getenv()`，类型自动转换，缺少必填项会在启动时立即报错而非运行时崩溃。

---

## 添加新技能

只需 3 个文件，无需修改任何配置——`SkillRegistry.auto_discover()` 会自动扫描并注册。

### 1. 创建目录结构

```
src/agent_platform/skills/my_skill/
├── __init__.py
├── skill.py
└── tools.py
```

### 2. 实现工具函数 (`tools.py`)

```python
async def my_domain_tool(query: str) -> list[dict]:
    """你的领域工具，接入外部 API / 数据库 / 模型等。"""
    # TODO: 替换为真实实现
    return [{"result": f"关于 {query} 的结果"}]
```

### 3. 实现技能类 (`skill.py`)

```python
from langchain_core.tools import tool
from langchain.agents import create_agent
from agent_platform.skills.base import BaseSkill
from .tools import my_domain_tool

SYSTEM_PROMPT = "你是一个 XX 领域的专业助手。..."

@tool
async def domain_search(query: str) -> str:
    """工具描述（LLM 会看到这段文字来决定是否调用）。"""
    results = await my_domain_tool(query)
    return str(results)

class MySkill(BaseSkill):
    @property
    def name(self) -> str:
        return "my_skill"

    @property
    def description(self) -> str:
        return "我的技能描述（路由器会看到这段文字来决定是否路由到此技能）"

    @property
    def examples(self) -> list[str]:
        return ["示例问题1", "示例问题2"]

    def create_agent(self, model_provider, checkpointer=None):
        model = model_provider.get_model()
        return create_agent(model, [domain_search], system_prompt=SYSTEM_PROMPT, checkpointer=checkpointer)

skill = MySkill()
```

### 4. 导出 (`__init__.py`)

```python
from .skill import skill
__all__ = ["skill"]
```

重启服务后，新技能自动出现在 `/skills` 列表中，路由器也能自动将相关问题分发到这个技能。

---

## 添加组合技能

组合技能通过 `compose()` 方法编排多个子 Agent，实现跨技能协作：

```python
class MyCompositeSkill(BaseSkill):
    @property
    def dependencies(self) -> list[str]:
        return ["skill_a", "skill_b"]

    def create_agent(self, model_provider):
        # 退化模式（依赖不可用时的降级方案）
        return create_agent(model_provider.get_model(), [], system_prompt="...")

    def compose(self, skills, model_provider):
        skill_a = skills.get("skill_a")
        skill_b = skills.get("skill_b")
        if not skill_a or not skill_b:
            return None  # 返回 None 触发退化到 create_agent()

        agent_a = skill_a.create_agent(model_provider)
        agent_b = skill_b.create_agent(model_provider)

        @tool
        async def call_a(query: str) -> str:
            """调用技能 A"""
            result = await agent_a.ainvoke({"messages": [HumanMessage(content=query)]})
            return result["messages"][-1].content

        @tool
        async def call_b(query: str) -> str:
            """调用技能 B"""
            result = await agent_b.ainvoke({"messages": [HumanMessage(content=query)]})
            return result["messages"][-1].content

        model = model_provider.get_model()
        return create_agent(model, [call_a, call_b], system_prompt="编排提示词...")
```

---

## 技术栈映射（与 PydanticAI 版对照）

本项目从 PydanticAI 版重写而来，以下是关键组件的对照表：

| 功能 | PydanticAI 版 | LangChain 版 |
|------|--------------|-------------|
| Agent 创建 | `pydantic_ai.Agent(model, system_prompt)` | `create_agent(model, tools, system_prompt)` |
| 工具注册 | `@agent.tool_plain` 装饰器 | `@langchain_core.tools.tool` 装饰器 |
| 工具执行 | Agent 内部自动管理 | LangGraph ReAct 循环自动管理 |
| 同步调用 | `await agent.run(message)` | `await agent.ainvoke({"messages": [...]})` |
| 流式调用 | `async with agent.run_stream()` | `agent.astream_events(..., version="v2")` |
| 结构化输出 | `Agent(output_type=Schema)` | `model.with_structured_output(Schema)` |
| 模型抽象 | `OpenAIChatModel` + 各 Provider | `ChatOpenAI` + `base_url` 参数 |
| 模型容错 | `FallbackModel([...])` | `model.with_fallbacks([...])` |
| 工作流编排 | `pydantic-graph GraphBuilder` | `langgraph.graph.StateGraph` |
| 依赖注入 | `deps_type=PlatformDeps` + `RunContext` | `PlatformDeps` dataclass + `app.state` |
| MCP 集成 | `MCPServerStdio` / `MCPServerStreamableHTTP` | `langchain-mcp-adapters.MultiServerMCPClient` |

---

## 测试

```bash
# 运行全部测试
pytest tests/ -v

# 运行特定测试文件
pytest tests/test_skills.py -v

# 运行特定测试类
pytest tests/test_orchestration.py::TestEventSerialization -v
```

测试覆盖（51 个用例）：
- **test_skills.py** — 技能注册中心、`get_all_skills()`、checkpointer 集成、SQL 注入校验（8 种攻击场景）、工具函数
- **test_router.py** — 路由决策模型验证、技能发现、`_build_router_prompt()` 输出、`_build_invoke_config()` session_id 行为
- **test_orchestration.py** — 事件序列化、执行计划往返、顺序图结构验证、sentinel 终止模式
- **test_multi_agent_router.py** — 多 Agent 模式、组合技能 compose 正常/退化路径、模型序列化往返
