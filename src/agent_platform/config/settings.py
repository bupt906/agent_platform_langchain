from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings


class ModelConfig(BaseSettings):
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"

    volcengine_api_key: str = ""
    volcengine_base_url: str = "https://ark.cn-beijing.volces.com/api/coding/v3"

    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com/v1"

    qwen_api_key: str = ""
    qwen_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"

    ollama_base_url: str = "http://localhost:11434/v1"

    model_config = {"env_file": ".env", "extra": "ignore"}


class Settings(BaseSettings):
    default_model: str = "volcengine:ark-code-latest"
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

    # ── Human-in-the-loop ──
    hitl_enabled: bool = True  # 全局启用/禁用 HITL
    hitl_approval_timeout: int = 300  # 审批超时（秒）
    hitl_sensitive_skills: list[str] = ["document_review"]  # 需审批的技能
    hitl_auto_approve_low_risk: bool = False  # 自动批准低风险操作

    # ── 审阅回调 ──
    callback_base_url: str = "http://192.168.22.231:28080"  # 审阅结果回调地址（为空则不发送回调）
    callback_auth_token: str = "ABC123XYZ"  # 回调时携带的 X-Auth-Token

    # ── 外部知识库（万悟平台 hit 检索接口）──
    kb_api_base_url: str = "http://10.77.100.102:8081"  # 知识库平台地址
    kb_api_key: str = "ww-f11218132a964b1389f56b07a3aa2f01"  # Bearer API Key
    kb_match_type: str = "mix"  # 检索模式：vector / text / mix
    kb_rerank_model_id: str = "2041688922286723072"  # 重排序模型 UUID（mix 模式可选）
    kb_priority_match: int = 0  # 权重匹配开关（mix 模式）：0=关闭 1=开启
    kb_semantics_priority: float = 0.2  # 语义权重（priority_match=1 时生效）
    kb_keyword_priority: float = 0.8  # 关键词权重（priority_match=1 时生效）
    kb_top_k: int = 5  # 返回结果数量
    kb_threshold: float = 0.4  # 相似度过滤阈值
    kb_use_graph: bool = False  # 是否使用知识图谱
    kb_request_timeout: float = 30.0  # hit 接口请求超时（秒）

    models: ModelConfig = Field(default_factory=ModelConfig)

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
