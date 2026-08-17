# 智能体中台（Agent Platform）

基于 LangChain / LangGraph 的智能体工作台。它把模型、Agent、声明式 Skill、工具、知识库、审计与人工审批连接在一起，提供可直接使用的 Web 界面和 FastAPI 接口。

## 你可以用它做什么

| 功能 | 说明 |
| --- | --- |
| 智能对话与自动路由 | 不选择 Agent 或 Skill 时，后端根据问题意图自动选择处理能力；也可手动指定。 |
| 流式执行反馈 | 对话通过 SSE 流式返回回答、路由结果、工具调用与可选的模型推理过程。 |
| 智能文档审阅 | 按句审阅文档，检索外部知识库，异步回调任务状态与审阅结果。 |
| 知识图谱抽取 | 通过声明式 Skill 从文档抽取实体、关系并生成图谱数据。 |
| CAD 参数化建模 | 通过隔离容器中的声明式 Skill 生成、检查和预览 STEP 等 CAD 产物。 |
| 多 Agent 编排 | 支持顺序、并行、动态编排，以及需要人工确认的执行流程。 |
| 记忆与偏好 | 保存会话、用户画像和工作台偏好；偏好包括主题、默认模型与 API 地址。 |
| 运营与用量 | 基于审计日志查看调用量、成功率、耗时、Token 消耗和近期活动。 |
| MCP 与 Skill 运行时 | 支持 MCP Server、工具超时、限流、调用预算、隔离 Workspace、容器 Sandbox 与 Artifact。 |

## 快速开始

### 1. 准备环境

- Python 3.11+
- Node.js LTS（仅运行 Web 前端时需要）
- 至少一个模型服务的 API Key，例如 DeepSeek、Qwen 或 OpenAI
- Docker 或兼容容器引擎（仅使用 CAD 等需要隔离 Runtime 的 Skill 时需要）

```bash
git clone <your-repository-url>
cd agent_platform_langchain

python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

cp .env.example .env
```

编辑 `.env`，最少配置一个模型：

```env
DEFAULT_MODEL=deepseek:deepseek-chat
DEEPSEEK_API_KEY=你的_API_Key
```

> 不要提交 `.env`、数据库文件或任何 API Key。

如果需要使用 CAD Skill，额外构建固定版本的隔离运行时：

```bash
bash setup_agentcad.sh
```

详细配置见 [CAD Skill 隔离运行时部署说明](docs/agentcad-部署说明.md)。镜像未就绪时，`/skills` 会把 CAD 标记为不可用，平台不会回退到宿主机执行模型生成代码。

### 2. 启动后端

```bash
uvicorn agent_platform.api.app:app --reload --host 0.0.0.0 --port 8000
```

后端启动后可访问：

- OpenAPI 文档：`http://localhost:8000/docs`
- 健康检查：`http://localhost:8000/health`

### 3. 启动 Web 前端

另开一个终端：

```bash
cd frontend
npm install
npm run dev
```

访问终端输出的本地地址（默认通常为 `http://localhost:3000`）。开发环境下前端会将 API 请求代理到 `http://localhost:8000`。

### 4. 第一次使用

1. 打开“智能对话”。
2. 直接输入任务即可；不选择 Agent / Skill 时会使用后端意图识别自动路由。
3. 需要精确控制时，在输入框上方选择一个 Agent 或 Skill。两者互斥。
4. 按需开启“推理”开关以查看模型返回的推理内容。
5. 在左下角“偏好设置”中设置主题、默认模型和后端 API 地址。

## 常用接口

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| `POST` | `/chat` | 同步对话 |
| `POST` | `/chat/stream` | SSE 流式对话，供 Web 对话页使用 |
| `GET` | `/skills` | 获取可用 Agent 与 Skill |
| `GET` | `/artifacts/{artifact_id}` | 访问 Skill 发布的安全产物或预览 |
| `POST` | `/review` | 提交异步文档审阅任务 |
| `GET` | `/audit` | 查询审计记录 |
| `GET` | `/audit/stats` | 获取运营统计 |
| `GET` / `PUT` | `/preferences/{profile_id}` | 读取或保存工作台偏好 |
| `GET` | `/hitl/approvals` | 查询待人工审批的任务 |
| `POST` | `/hitl/approvals/{id}/decide` | 批准或拒绝任务 |
| `GET` | `/health` | 健康检查 |

完整字段说明和在线调试请使用启动后的 `/docs`。

### 自动路由与指定能力

```bash
# 不传 Agent / Skill：由后端识别意图并自动路由
curl -X POST http://localhost:8000/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"message":"请分析任务并选择合适的处理方式","response_mode":"auto"}'

# 指定 Python Agent
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"审阅这份安全生产方案","agent":"document_review"}'

# 指定声明式 Skill
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"从文档抽取实体和关系","skill":"knowledge-graph-extraction"}'
```

`ChatRequest` 的常用字段：

| 字段 | 说明 |
| --- | --- |
| `message` | 用户问题，必填 |
| `agent` / `skill` | 可选；显式指定处理能力，二选一 |
| `model` | 可选；覆盖后端或偏好中的默认模型 |
| `session_id` | 可选；用于连续对话、记忆与审计关联 |
| `profile_id` | 可选；用于读取已保存的用户偏好 |
| `response_mode` | 未指定能力时为 `auto`（意图路由）或 `general`（通用回答） |
| `thinking` | 是否流式返回推理内容 |

### 文档审阅

`POST /review` 接收文件路径、知识库 ID 与任务 ID，接口会立即返回 `accepted`；审阅任务随后在后台执行，并通过回调报告状态：

- `520`：审阅中
- `530`：审阅完成
- `777`：审阅失败

```bash
curl -X POST http://localhost:8000/review \
  -H "Content-Type: application/json" \
  -d '{
    "task_id": 1001,
    "file_path": "/absolute/path/to/document.docx",
    "kb_ids": ["knowledge-base-id"]
  }'
```

审阅结果可通过 `/api/callback/batch/{task_id}` 查询。外部知识库连接参数通过 `.env` 中的 `KB_*` 配置；接口字段和在线调试以启动后的 OpenAPI `/docs` 为准。

### 工作台偏好

偏好按浏览器生成的 `profile_id` 隔离，并同时持久化到浏览器与后端 SQLite：

```bash
curl http://localhost:8000/preferences/demo-user

curl -X PUT http://localhost:8000/preferences/demo-user \
  -H "Content-Type: application/json" \
  -d '{
    "theme": "dark",
    "default_model": "deepseek:deepseek-chat",
    "api_base_url": ""
  }'
```

开发环境中 API 基础地址留空即可使用 Vite 代理；独立部署前端时可填写后端地址。

## 知识库能力

知识库是平台的公共能力，注册在全局工具表里，**任何 Agent 或 Skill 都可以直接使用**，
不需要自己写客户端，也不需要知道后端是谁。

> 开发新智能体时如何调用知识库，见 **[知识库接入指南](docs/知识库接入指南.md)**——
> 含三种接入方式的完整示例、prompt 写法与迁移 runbook。

| 工具 | 用途 |
| --- | --- |
| `search_knowledge` | 检索知识库，返回原文证据片段 |
| `answer_from_knowledge` | 让知识库直接作答并给出来源 |
| `list_knowledge_bases` | 列出可检索的知识库，供 Agent 选择范围 |
| `fetch_knowledge_document` | 按原文顺序取回某文档全文 |
| `add_to_knowledge_base` | 把文本写入知识库（有副作用） |

声明式 Skill 在 `SKILL.md` 的 frontmatter 里声明即可绑定：

```yaml
---
name: my-skill
description: ...
tools: [search_knowledge, read_file, write_file]
---
```

Python Agent 从工具注册表取用：

```python
from agent_platform.tools import registry

tools = registry.get_many(["search_knowledge", "list_knowledge_bases"])
```

需要直接持有后端时（例如自定义流水线），用 `deps.knowledge`，它是
`KnowledgeProvider` 接口而不是某个具体实现。

### 后端与切换

`KNOWLEDGE_PROVIDER` 决定由谁提供知识库能力，调用方代码不受影响：

| 取值 | 后端 | 说明 |
| --- | --- | --- |
| `wanwu` | 万悟平台 hit 接口 | 默认值，配置见 `KB_*` |
| `omnimind` | 知识库中台服务契约层 | 配置见 `OMNIMIND_*`，需安装 `kb-sdk` |
| `dual` | 两者并行 | 返回 `omnimind` 的结果，把与 `wanwu` 的差异写入日志，供迁移期比对 |

不同后端能力有差异：`wanwu` 只支持检索，服务端问答、取全文、写入知识库需要 `omnimind`。
工具会如实说明「后端不支持」，不会编造结果。

切到知识库中台的完整步骤（含前置条件、双跑观察与回退）见
[知识库接入指南 · 迁移到知识库中台](docs/知识库接入指南.md#迁移到知识库中台)。概要：

```bash
pip install -e ".[omnimind]"      # kb-sdk 由知识库中台仓库的 sdk/ 构建
# .env 中设置 OMNIMIND_BASE_URL 与 OMNIMIND_API_KEY（对应中台的 SERVICE_API_KEY）
# 把 KNOWLEDGE_PROVIDER 改为 dual 观察一段时间，再改为 omnimind
```

如果外部系统仍在使用旧平台的知识库 ID（例如审阅任务的下发方），用
`OMNIMIND_KB_ID_MAP=旧id:新UUID,旧id2:新UUID2` 做迁移期映射。未配置映射的旧格式 ID 会被
明确拒绝，而不是发到中台换回一个语焉不详的 403。

### 检索失败与「没有找到」是两回事

工具在检索失败时返回明确的错误文本，绝不返回「未检索到相关内容」。后端部分不可用时
（例如向量检索挂了但字面检索还在），结果会带上降级说明。这一点在文档审阅里尤其重要：
把「没查成」当成「无问题」会直接产出错误结论。

## 系统结构

```text
frontend/                     React + Vite 工作台
src/agent_platform/
├── api/                      FastAPI、SSE、审阅/偏好/审计等接口
├── agents/                   Python Agent（当前包含文档审阅）
├── config/                   配置与后端选择
├── prompts/                  分层 Prompt 构建与模板
├── skills/                   声明式 Skill（当前包含知识图谱抽取与 CAD）
├── runtime/                  Skill Workspace、Runtime Profile、Sandbox 与 Artifact
├── core/                     注册中心、意图路由与依赖容器
├── graph/                    多 Agent 编排
├── models/                   DeepSeek、Qwen、OpenAI、Ollama 适配
├── knowledge/                知识库能力：统一接口 + 可切换后端（万悟 / 知识库中台）
├── memory/                   会话、摘要与用户画像持久化
├── audit/                    审计记录与统计
├── hitl/                     Human-in-the-Loop 审批
├── tools/                    文件、可信脚本、Python 子进程及 Runtime 工具
└── mcp_servers/              MCP Server 注册与动态加载
tests/                        后端测试
docker/                       Skill Runtime 镜像定义
docs/                         开发指南、知识库接入指南与专项部署说明
```

一次对话的主要流程：

1. 前端发送问题及可选的 Agent、Skill、模型、会话和偏好 ID。
2. 若未指定能力，路由器执行意图识别并选择通用回答、Skill 或编排计划。
3. Agent / Skill 调用模型、工具、知识库或 MCP 服务；声明 Runtime 的 Skill 会进入隔离 Workspace 和容器 Sandbox。
4. SSE 将路由、工具动态、Artifact 和回答持续返回给前端。
5. 会话、用户偏好与审计指标按配置持久化。

## 重要配置

所有可配置项见 [.env.example](.env.example)。最常用的配置如下：

| 配置 | 说明 |
| --- | --- |
| `DEFAULT_MODEL` | 默认模型，格式如 `deepseek:deepseek-chat` |
| `DEEPSEEK_API_KEY` / `QWEN_API_KEY` / `OPENAI_API_KEY` | 对应模型服务的凭据 |
| `MCP_CONFIG_PATH` | MCP Server 配置文件路径 |
| `MEMORY_DB_PATH` / `AUDIT_DB_PATH` | 会话偏好与审计 SQLite 文件位置 |
| `API_KEY` | API 鉴权密钥；留空则不启用鉴权 |
| `RATE_LIMIT_PER_MINUTE` | 每个 IP 每分钟的最大请求数，`0` 为不限流 |
| `KNOWLEDGE_PROVIDER` | 知识库后端：`wanwu` / `omnimind` / `dual` |
| `KB_API_BASE_URL` / `KB_API_KEY` | 万悟平台知识库地址与凭据（`wanwu` 后端）|
| `OMNIMIND_BASE_URL` / `OMNIMIND_API_KEY` | 知识库中台地址与服务密钥（`omnimind` 后端）|
| `CALLBACK_BASE_URL` / `CALLBACK_AUTH_TOKEN` | 文档审阅任务的回调地址与鉴权信息 |
| `SKILL_WORKSPACE_ROOT` / `SKILL_ARTIFACT_ROOT` | 隔离工作区与已发布产物根目录 |
| `SKILL_SANDBOX_ENGINE` | Skill 容器运行时，默认 `docker` |
| `CAD_RUNTIME_IMAGE` | CAD Runtime 的固定版本镜像 |

生产部署前请至少完成以下事项：

- 使用环境变量或密钥管理服务配置凭据，不在代码或镜像中保存密钥。
- 将 CORS 允许来源限制为实际前端域名。
- 为 SQLite 数据库设置备份、保留和访问权限策略；高并发场景建议替换为外部数据库。
- 多 worker / 多实例部署时，为 `SKILL_ARTIFACT_ROOT` 配置共享持久卷。
- 可执行 Skill 应使用独立 Runtime Profile 和不可变镜像，不要扩大全局 `bash` 白名单。
- 通过反向代理提供 HTTPS，并为 API 设置合适的认证与限流策略。

## 开发、测试与扩展

```bash
# 后端测试
.venv/bin/python -m pytest -q

# 后端静态检查
.venv/bin/python -m ruff check src tests

# 前端检查与构建
cd frontend
npm run lint
npm run build
```

- 添加 Python Agent：在 `src/agent_platform/agents/` 下创建目录，注册中心会自动发现。
- 添加声明式 Skill：在 `src/agent_platform/skills/` 下创建包含 `SKILL.md` 的目录；需要执行模型生成代码时必须同时定义 Runtime Profile。
- 配置或扩展 MCP：编辑 [mcp_config.json](mcp_config.json)。
- 完整扩展规则见 [开发者指南](docs/developer-guide.md)。

## 许可与安全说明

本项目可执行工具调用、文件访问和外部服务请求。上线前请按实际业务范围收紧工具白名单、文件目录、网络访问、CORS、认证和审计保留策略。
