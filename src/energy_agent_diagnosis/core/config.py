"""使用分组配置描述阶段 1 及后续阶段需要的稳定配置边界。"""

from functools import lru_cache
from typing import Literal

from pydantic import BaseModel, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from energy_agent_diagnosis.contracts import ProviderType, Role


class AppSettings(BaseModel):
    """FastAPI 应用的基本运行设置。"""

    name: str = "energy-agent-diagnosis"
    version: str = "0.1.0"
    environment: Literal["development", "test", "production"] = "development"
    debug: bool = False
    host: str = "127.0.0.1"
    port: int = Field(default=8000, ge=1, le=65535)
    openapi_enabled: bool = True


class LoggingSettings(BaseModel):
    """结构化日志输出设置。"""

    level: str = "INFO"
    json_output: bool | None = None

    def uses_json(self, environment: str) -> bool:
        """测试和生产强制 JSON；开发环境允许显式选择输出形式。"""
        if environment != "development":
            return True
        return bool(self.json_output)


class ApiKeyRecord(BaseModel):
    """把一个 API Key 安全映射到标准用户和角色。"""

    key: SecretStr
    user_id: str
    roles: frozenset[Role]


class AuthSettings(BaseModel):
    """阶段 1 的可替换 API Key 认证设置。"""

    enabled: bool = True
    api_keys: list[ApiKeyRecord] = Field(default_factory=list)


class ProviderSettings(BaseModel):
    """为八类 Provider 保留独立的 Mock/Real 切换点。"""

    device_profile: ProviderType = ProviderType.MOCK
    alarm: ProviderType = ProviderType.MOCK
    timeseries: ProviderType = ProviderType.MOCK
    manual_search: ProviderType = ProviderType.MOCK
    ticket_search: ProviderType = ProviderType.MOCK
    graph_relation: ProviderType = ProviderType.MOCK
    ticket_write: ProviderType = ProviderType.MOCK
    case_review: ProviderType = ProviderType.MOCK


class ModelSettings(BaseModel):
    """后续模型调用需要的配置占位；阶段 1 不发起调用。"""

    model_name: str = "not-configured"
    endpoint: str = ""
    timeout_seconds: float = Field(default=30, gt=0)


class RetrievalSettings(BaseModel):
    """阶段 3 RAG 检索链路的策略配置。"""

    keyword_backend: Literal["opensearch", "elasticsearch"] = "opensearch"
    recall_top_k: int = Field(default=20, ge=1, le=100)
    rerank_top_n: int = Field(default=30, ge=1, le=100)
    final_top_k: int = Field(default=5, ge=1, le=50)
    score_threshold: float = Field(default=0.45, ge=0, le=1)
    manual_source_weight: float = Field(default=0.95, ge=0, le=1)
    ticket_source_weight: float = Field(default=0.9, ge=0, le=1)
    graph_source_weight: float = Field(default=0.65, ge=0, le=1)
    weak_evidence_penalty: float = Field(default=0.7, ge=0, le=1)
    verified_evidence_boost: float = Field(default=0.08, ge=0, le=0.3)
    enable_graph_recall: bool = True
    enable_vector_recall: bool = True
    min_strong_evidence_count: int = Field(default=1, ge=0, le=10)
    max_quote_chars: int = Field(default=180, ge=40, le=1000)

    # Stage 3 extended configurations
    manual_search_endpoint: str = ""
    ticket_search_endpoint: str = ""
    graph_relation_endpoint: str = ""
    qwen_rewrite_endpoint: str = ""
    reranker_endpoint: str = ""
    manual_score_threshold: float | None = Field(default=None, ge=0, le=1)
    ticket_score_threshold: float | None = Field(default=None, ge=0, le=1)
    fallback_keyword_weight: float = Field(default=0.45, ge=0, le=1)
    fallback_vector_weight: float = Field(default=0.55, ge=0, le=1)
    dedup_limit: int = Field(default=10, ge=1, le=100)


class DependencyEndpoint(BaseModel):
    """描述一个可通过 TCP、HTTP 或 Redis 协议探测的依赖。"""

    enabled: bool = False
    required: bool = False
    protocol: Literal["tcp", "http", "redis"] = "tcp"
    host: str = "127.0.0.1"
    port: int | None = Field(default=None, ge=1, le=65535)
    url: str | None = None

    @model_validator(mode="after")
    def validate_target(self) -> "DependencyEndpoint":
        """确保已启用的探测配置具有对应协议所需的目标。"""
        if not self.enabled:
            return self
        if self.protocol == "http" and not self.url:
            raise ValueError("HTTP 依赖必须配置 url")
        if self.protocol != "http" and self.port is None:
            raise ValueError("TCP/Redis 依赖必须配置 port")
        return self


class DependencySettings(BaseModel):
    """阶段 1 完整基础设施的依赖探测配置。"""

    mysql: DependencyEndpoint = Field(default_factory=DependencyEndpoint)
    redis: DependencyEndpoint = Field(default_factory=DependencyEndpoint)
    minio: DependencyEndpoint = Field(default_factory=DependencyEndpoint)
    rabbitmq: DependencyEndpoint = Field(default_factory=DependencyEndpoint)
    milvus: DependencyEndpoint = Field(default_factory=DependencyEndpoint)
    neo4j: DependencyEndpoint = Field(default_factory=DependencyEndpoint)
    influxdb: DependencyEndpoint = Field(default_factory=DependencyEndpoint)
    opensearch: DependencyEndpoint = Field(default_factory=DependencyEndpoint)

    def enabled_items(self) -> list[tuple[str, DependencyEndpoint]]:
        """返回需要执行 readiness 探测的依赖。"""
        return [
            (name, endpoint)
            for name, endpoint in (
                ("mysql", self.mysql),
                ("redis", self.redis),
                ("minio", self.minio),
                ("rabbitmq", self.rabbitmq),
                ("milvus", self.milvus),
                ("neo4j", self.neo4j),
                ("influxdb", self.influxdb),
                ("opensearch", self.opensearch),
            )
            if endpoint.enabled
        ]


class HealthSettings(BaseModel):
    """依赖健康探测的统一超时设置。"""

    probe_timeout_seconds: float = Field(default=2, gt=0, le=30)


class MetricsSettings(BaseModel):
    """Prometheus 指标暴露设置。"""

    enabled: bool = True
    path: str = Field(default="/metrics", pattern=r"^/[A-Za-z0-9/_-]+$")
    namespace: str = "energy_diagnosis"


class Settings(BaseSettings):
    """聚合全部配置分组，并支持 ``EDA_`` 嵌套环境变量。"""

    model_config = SettingsConfigDict(
        env_prefix="EDA_",
        env_nested_delimiter="__",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app: AppSettings = Field(default_factory=AppSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)
    auth: AuthSettings = Field(default_factory=AuthSettings)
    providers: ProviderSettings = Field(default_factory=ProviderSettings)
    model: ModelSettings = Field(default_factory=ModelSettings)
    retrieval: RetrievalSettings = Field(default_factory=RetrievalSettings)
    dependencies: DependencySettings = Field(default_factory=DependencySettings)
    health: HealthSettings = Field(default_factory=HealthSettings)
    metrics: MetricsSettings = Field(default_factory=MetricsSettings)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """读取并缓存进程级配置，测试可清理缓存后重新加载。"""
    return Settings()
