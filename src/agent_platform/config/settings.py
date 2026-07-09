from __future__ import annotations

from pathlib import Path

from pydantic import Field
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


class Settings(BaseSettings):
    default_model: str = "deepseek:deepseek-chat"
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

    # ── 技能手册 ──
    skill_manual_path: str = "skill_manuals"  # 技能手册 .md 文件目录
    skill_manual_enabled: bool = True  # 是否启用手册匹配

    # ── Human-in-the-loop ──
    hitl_enabled: bool = True  # 全局启用/禁用 HITL
    hitl_approval_timeout: int = 300  # 审批超时（秒）
    hitl_sensitive_skills: list[str] = ["data_query", "contract_review"]  # 需审批的技能
    hitl_auto_approve_low_risk: bool = False  # 自动批准低风险操作

    # ── 向量 RAG ──
    embedding_model: str = ""  # embedding 模型（空=复用 default_model 同 provider 的 embedding）
    embedding_dimensions: int = 1536  # 向量维度（deepseek=1536, qwen=1024）
    kb_vector_top_k: int = 5  # 向量检索 top-k
    kb_vector_threshold: float = 0.7  # 余弦距离阈值（0=完全匹配，2=相反，默认0.7）

    models: ModelConfig = Field(default_factory=ModelConfig)

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
