"""Single typed boundary for runtime configuration assembly."""

from __future__ import annotations

import os
from enum import StrEnum
from typing import Any, Final, Self

from pydantic import Field, HttpUrl, model_validator

from energy_agent.contracts.common import StrictModel


class DeploymentProfile(StrEnum):
    DEV = "dev"
    FULL = "full"
    STAGING = "staging"
    PRODUCTION = "production"
    LIVE = "live"


PROTECTED_PROFILES: Final = {
    DeploymentProfile.FULL,
    DeploymentProfile.STAGING,
    DeploymentProfile.PRODUCTION,
    DeploymentProfile.LIVE,
}
APPROVED_MODEL_TUPLES: Final = {
    ("openai", "gpt-4o-mini", "https://api.openai.com/v1/chat/completions"),
    (
        "aliyun",
        "qwen-plus",
        "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
    ),
}
FORBIDDEN_RUNTIME_MARKERS: Final = (
    "mock",
    "fixture",
    "sandbox",
    "gold",
    "d3_dev",
    ".json",
    ":memory:",
    "in-memory",
    "in_memory",
)
PLACEHOLDER_REFERENCES: Final = {"", "change-me", "changeme", "example", "placeholder", "todo"}


class SecretReference(StrictModel):
    env_name: str = Field(pattern=r"^[A-Z][A-Z0-9_]*$")
    secret_ref: str

    @model_validator(mode="after")
    def reject_placeholder(self) -> Self:
        if self.secret_ref.strip().lower() in PLACEHOLDER_REFERENCES:
            raise ValueError("secret reference is a placeholder")
        return self


class AppConfig(StrictModel):
    name: str = "energy-agent-diagnosis"
    endpoint: HttpUrl
    runtime_source: str = "service"


class AuthConfig(StrictModel):
    issuer: HttpUrl
    audience: str
    client_secret: SecretReference


class MySQLConfig(StrictModel):
    endpoint: str
    database: str
    username: str
    password: SecretReference


class RedisConfig(StrictModel):
    endpoint: str
    password: SecretReference
    key_prefix: str = "diag"


class StorageConfig(StrictModel):
    endpoint: HttpUrl
    bucket: str
    access_key: SecretReference
    secret_key: SecretReference


class ModelGatewayConfig(StrictModel):
    provider: str
    model: str
    endpoint: HttpUrl
    api_key: SecretReference


class RetrievalConfig(StrictModel):
    endpoint: HttpUrl
    provider: str = "retrieval-api"


class ObservabilityConfig(StrictModel):
    endpoint: HttpUrl
    provider: str = "langfuse"
    public_key: SecretReference
    secret_key: SecretReference


class RuntimeConfig(StrictModel):
    deployment_profile: DeploymentProfile
    app: AppConfig
    auth: AuthConfig
    control_mysql: MySQLConfig
    ops_mysql: MySQLConfig
    redis: RedisConfig
    storage: StorageConfig
    model_gateway: ModelGatewayConfig
    retrieval: RetrievalConfig
    observability: ObservabilityConfig

    @model_validator(mode="after")
    def protected_profile_rules(self) -> Self:
        if self.deployment_profile not in PROTECTED_PROFILES:
            return self
        selectors = (
            self.app.runtime_source,
            self.control_mysql.endpoint,
            self.ops_mysql.endpoint,
            self.model_gateway.provider,
            self.retrieval.provider,
        )
        forbidden = [
            selector
            for selector in selectors
            if any(marker in selector.lower() for marker in FORBIDDEN_RUNTIME_MARKERS)
        ]
        if forbidden:
            raise ValueError("protected profile selects a forbidden runtime source")
        model_tuple = (
            self.model_gateway.provider,
            self.model_gateway.model,
            str(self.model_gateway.endpoint),
        )
        if model_tuple not in APPROVED_MODEL_TUPLES:
            raise ValueError("protected profile model tuple is not approved")
        return self

    @classmethod
    def from_environment(cls, environment: dict[str, str] | None = None) -> RuntimeConfig:
        """Assemble config from one environment JSON value at the sole boundary."""

        import json

        source = dict(os.environ) if environment is None else environment
        raw = source.get("ENERGY_AGENT_CONFIG_JSON")
        if raw is None:
            raise ValueError("ENERGY_AGENT_CONFIG_JSON is required")
        value: Any = json.loads(raw)
        return cls.model_validate(value)
