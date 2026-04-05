"""Application settings."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


ENV_PATH = Path(__file__).resolve().parents[3] / ".env"


class GraphQuizSettings(BaseSettings):
    """Runtime settings loaded from environment for the standalone project."""

    model_config = SettingsConfigDict(
        env_file=str(ENV_PATH),
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    llm_base_url: str = Field(default="", alias="SOMNI_LLM_BASE_URL")
    llm_api_key: str = Field(default="", alias="SOMNI_LLM_API_KEY")
    llm_model: str = Field(default="doubao-seed-2-0-mini-260215", alias="SOMNI_LLM_MODEL")
    llm_temperature: float = Field(default=0.2, alias="SOMNI_LLM_TEMPERATURE")
    llm_timeout: int = Field(default=30, alias="SOMNI_LLM_TIMEOUT")
    llm_reasoning_effort: str = Field(default="minimal", alias="SOMNI_LLM_REASONING_EFFORT")
    grpc_host: str = Field(default="0.0.0.0", alias="SOMNI_GRPC_HOST")
    grpc_port: int = Field(default=19000, alias="SOMNI_GRPC_PORT")

    @property
    def llm_ready(self) -> bool:
        return bool(self.llm_base_url and self.llm_api_key and self.llm_model)

    @property
    def missing_llm_config_keys(self) -> list[str]:
        missing: list[str] = []
        if not self.llm_base_url:
            missing.append("SOMNI_LLM_BASE_URL")
        if not self.llm_api_key:
            missing.append("SOMNI_LLM_API_KEY")
        if not self.llm_model:
            missing.append("SOMNI_LLM_MODEL")
        return missing


@lru_cache(maxsize=1)
def get_settings() -> GraphQuizSettings:
    """Load and cache application settings."""
    return GraphQuizSettings()
