from __future__ import annotations

from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings


class ModelConfig(BaseSettings):
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"

    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com/v1"

    qwen_api_key: str = ""
    qwen_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"

    ollama_base_url: str = "http://localhost:11434/v1"

    model_config = {"env_file": ".env", "extra": "ignore"}


class WanwuKnowledgeConfig(BaseSettings):
    """万悟平台 hit 接口的连接与检索参数。

    这些字段全部是万悟专有的，不该出现在 Settings 顶层——顶层只保留跨后端通用的选择项，
    否则每接一个新后端都会往全局配置里堆一批别的后端用不上的字段。
    """

    base_url: str = Field(
        default="http://localhost:8081",
        validation_alias=AliasChoices("KB_API_BASE_URL", "KB_BASE_URL"),
    )
    api_key: str = ""  # Bearer API Key
    match_type: str = "mix"  # 检索模式：vector / text / mix
    rerank_model_id: str = ""  # 重排序模型 UUID（mix 模式可选）
    priority_match: int = 0  # 权重匹配开关（mix 模式）：0=关闭 1=开启
    semantics_priority: float = 0.2  # 语义权重（priority_match=1 时生效）
    keyword_priority: float = 0.8  # 关键词权重（priority_match=1 时生效）
    top_k: int = 5  # 返回结果数量
    threshold: float = 0.4  # 相似度过滤阈值
    use_graph: bool = False  # 是否使用知识图谱
    request_timeout: float = 30.0  # hit 接口请求超时（秒）
    retries: int = 1  # 可重试错误的重试次数

    # populate_by_name 让 base_url 既能由 KB_API_BASE_URL 环境变量注入，
    # 也能在测试和程序里按字段名直接构造；否则 validation_alias 会顶掉字段名。
    model_config = {
        "env_file": ".env",
        "extra": "ignore",
        "env_prefix": "KB_",
        "populate_by_name": True,
    }


class OmniMindKnowledgeConfig(BaseSettings):
    """知识库中台（万象智库 OmniMind）服务契约层的连接参数。"""

    base_url: str = "http://localhost:8000"  # 知识库中台地址
    api_key: str = ""  # 服务密钥，对应中台的 SERVICE_API_KEY
    top_k: int = 5  # 默认返回的证据条数
    request_timeout: float = 30.0
    retries: int = 2
    # 旧知识库 ID → 中台 UUID 的映射，格式 "旧id:新id,旧id2:新id2"。
    # 迁移期用来让沿用旧 ID 的外部调用方（如审阅任务）不必同步改造。
    kb_id_map: str = ""

    model_config = {"env_file": ".env", "extra": "ignore", "env_prefix": "OMNIMIND_"}


class Settings(BaseSettings):
    default_model: str = "deepseek:deepseek-v4-pro"
    mcp_config_path: Path = Path("mcp_config.json")
    log_level: str = "INFO"
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # 可靠性配置
    request_timeout: int = 120  # 模型请求超时（秒）
    max_retries: int = 2  # 模型请求失败重试次数

    # 安全配置
    api_key: str = ""  # API 认证密钥，为空则不启用认证

    # 限流配置
    rate_limit_per_minute: int = 60  # 每 IP 每分钟最大请求数

    # ── 持久化记忆 ──
    memory_db_path: str = "memory.db"  # SQLite 记忆数据库路径
    memory_retention_days: int = 90  # 对话历史保留天数
    auto_summarize_threshold: int = 10  # 触发自动总结的轮次阈值
    summarization_model: str = ""  # 总结专用模型（空=复用 default_model）
    enable_profile_persistence: bool = True  # 是否启用用户画像持久化

    # ── 审计日志 ──
    audit_db_path: str = "audit.db"  # 审计日志数据库路径
    audit_log_retention_days: int = 365  # 审计日志保留天数
    audit_log_tool_calls: bool = True  # 是否记录工具调用详情
    audit_log_token_usage: bool = True  # 是否记录 Token 用量

    # ── Prompt 缓存 ──
    prompt_cache_enabled: bool = True  # 是否启用分层 prompt
    prompt_cache_ttl: int = 300  # 稳定层缓存 TTL（秒）

    # ── Tool 优化 ──
    tool_parallel_execution: bool = True  # 单轮次内并行工具调用
    tool_timeout_seconds: float = 30.0  # 单个工具调用超时（秒）
    tool_rate_limit_per_minute: int = 100  # 全局工具调用速率限制
    tool_budget_max_calls: int = 50  # 单次对话最大工具调用次数
    mcp_dynamic_reload: bool = True  # 运行时重载 MCP 工具

    # ── 声明式 Skills ──
    declarative_skills_enabled: bool = True  # 是否启用声明式 Skill 系统
    declarative_skills_max_tool_calls: int = 10  # Skill 执行的工具调用上限
    python_sandbox_timeout: int = 30  # execute_python 超时秒数
    file_read_allowed_roots: str = "."  # 逗号分隔的允许读取目录
    file_read_max_chars: int = 50_000  # read_file 单次最多返回字符数
    file_read_max_bytes: int = 10 * 1024 * 1024  # read_file 可读取的最大文件大小(10mb)
    file_write_allowed_roots: str = "."  # 逗号分隔的允许写入目录
    file_write_max_bytes: int = 10 * 1024 * 1024  # write_file 单次最大写入大小(10mb)
    bash_allowed_roots: str = "."  # bash 工具允许访问的目录
    bash_allowed_commands: str = "python,python3,pytest,ruff,ls,find,mkdir"  # 允许执行的命令名
    bash_default_timeout_seconds: int = 120
    bash_max_timeout_seconds: int = 300
    bash_max_output_chars: int = 15_000

    # ── Skill 安全运行时 ──
    skill_workspace_root: Path = Path(".agent-platform/workspaces")
    skill_artifact_root: Path = Path(".agent-platform/artifacts")
    skill_artifact_ttl_seconds: int = 7 * 24 * 60 * 60
    skill_artifact_max_bytes: int = 50 * 1024 * 1024
    skill_sandbox_engine: str = "docker"
    cad_skill_enabled: bool = True
    cad_runtime_image: str = "agent-platform/agentcad:0.4.0"
    cad_runtime_timeout_seconds: int = 300
    cad_runtime_memory_mb: int = 2048
    cad_runtime_cpus: float = 2.0
    cad_runtime_pids_limit: int = 64

    # ── Human-in-the-loop ──
    hitl_enabled: bool = True  # 全局启用/禁用 HITL
    hitl_approval_timeout: int = 300  # 审批超时（秒）
    hitl_sensitive_skills: list[str] = ["document_review"]  # 需审批的技能
    hitl_auto_approve_low_risk: bool = False  # 自动批准低风险操作

    # ── 审阅回调 ──
    callback_base_url: str = ""  # 审阅结果回调地址（为空则不发送回调）
    callback_auth_token: str = ""  # 回调时携带的 X-Auth-Token

    # ── 知识库后端 ──
    # 选择哪个后端提供知识库能力。切换只改这一项，调用方（Agent / Skill / 审阅流水线）不变。
    #   wanwu    — 万悟平台 hit 接口（迁移前的既有后端）
    #   omnimind — 知识库中台的 /api/v1/service 契约层
    #   dual     — 两边都查，用 omnimind 的结果，把差异写入日志供迁移期比对
    knowledge_provider: str = "wanwu"

    models: ModelConfig = Field(default_factory=ModelConfig)
    wanwu: WanwuKnowledgeConfig = Field(default_factory=WanwuKnowledgeConfig)
    omnimind: OmniMindKnowledgeConfig = Field(default_factory=OmniMindKnowledgeConfig)

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
