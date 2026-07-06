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

    models: ModelConfig = Field(default_factory=ModelConfig)

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
