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

    output_dir: Path = Path("./generated_projects")
    log_dir: Path = Path("./logs")  # 日志文件目录，便于排查问题
    log_level: str = "INFO"
    llm_timeout: int = 120  # LLM 请求超时秒数
    use_planning: bool = True  # False 时跳过规划，使用旧版整体生成（更快）


settings = Settings()
