from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "energy-agent"
    app_env: str = "local"
    log_level: str = "INFO"
    log_format: Literal["console", "json"] = "console"
    mysql_dsn: str = "mysql+asyncmy://energy:energy_dev@localhost:3306/energy_agent"
    redis_url: str = "redis://localhost:6379/0"
    redis_session_ttl_seconds: int = Field(default=86_400, gt=0)
    influxdb_url: str = "http://localhost:8086"
    influxdb_token: str = "energy-token"
    influxdb_org: str = "energy"
    influxdb_bucket: str = "energy_metrics"
    influxdb_query_timeout_seconds: float = Field(default=5.0, gt=0)
    default_diagnosis_window_minutes: int = Field(default=30, gt=0)
    model_mode: Literal["disabled", "openai_compatible"] = "disabled"
    model_gateway_base_url: str | None = None
    model_gateway_api_key: str | None = None
    model_name: str = "qwen2.5-72b"
    model_timeout_seconds: float = Field(default=15.0, gt=0)
    model_temperature: float = Field(default=0.2, ge=0, le=0.3)
    observability_mode: Literal["local", "langfuse"] = "local"
    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None
    langfuse_host: str = "https://cloud.langfuse.com"
    trace_content_mode: Literal["none", "metadata_only", "truncated"] = "metadata_only"

    @model_validator(mode="after")
    def validate_langfuse_credentials(self) -> "Settings":
        if self.observability_mode == "langfuse" and not (
            self.langfuse_public_key and self.langfuse_secret_key
        ):
            raise ValueError(
                "LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY are required "
                "when OBSERVABILITY_MODE=langfuse"
            )
        if self.model_mode == "openai_compatible" and not (
            self.model_gateway_base_url and self.model_gateway_api_key
        ):
            raise ValueError(
                "MODEL_GATEWAY_BASE_URL and MODEL_GATEWAY_API_KEY are required "
                "when MODEL_MODE=openai_compatible"
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
