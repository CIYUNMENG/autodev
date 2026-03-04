"""应用配置"""
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用配置"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # LLM 提供方: openai | doubao
    llm_provider: str = "openai"

    # OpenAI 配置
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o-mini"

    # 豆包/火山引擎 Ark 配置
    ark_api_key: str = ""
    ark_base_url: str = "https://ark.cn-beijing.volces.com/api/v3"
    ark_model: str = "doubao-seed-1-6-251015"

    # LiteLLM 可选覆盖：直接指定模型字符串，如 openai/gpt-4o、volcengine/doubao-xxx
    litellm_model: str = ""

    output_dir: Path = Path("./generated_projects")
    log_dir: Path = Path("./logs")  # 日志文件目录，便于排查问题
    log_level: str = "INFO"
    llm_timeout: int = 120  # LLM 请求超时秒数

    # 存储限制与淘汰
    task_store_max_size: int = 1000  # 任务数上限，超出时按 updated_at 淘汰最旧
    chat_store_max_sessions: int = 200  # 会话数上限，超出时按 updated_at 淘汰最旧


settings = Settings()
