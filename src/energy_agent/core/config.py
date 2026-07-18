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
    model_mode: Literal["disabled", "openai_compatible", "openai"] = "disabled"
    model_gateway_base_url: str | None = None
    model_gateway_api_key: str | None = None
    openai_base_url: str = "https://api.openai.com"
    openai_api_key: str | None = None
    model_name: str = "gpt-5.6-terra"
    model_timeout_seconds: float = Field(default=15.0, gt=0)
    model_temperature: float = Field(default=0.2, ge=0, le=0.3)
    observability_mode: Literal["local", "langfuse"] = "local"
    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None
    langfuse_host: str = "https://cloud.langfuse.com"
    trace_content_mode: Literal["none", "metadata_only", "truncated"] = "metadata_only"
    retrieval_mode: Literal["keyword_only", "hybrid"] = "keyword_only"
    query_rewrite_mode: Literal["rules", "model_enhanced"] = "rules"
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "energy"
    minio_secret_key: str = "energy_minio_dev"
    minio_bucket_documents: str = "energy-documents"
    minio_secure: bool = False
    milvus_uri: str = "http://localhost:19530"
    milvus_token: str | None = None
    milvus_manual_collection: str = "manual_chunks"
    milvus_ticket_collection: str = "ticket_cases"
    milvus_vector_dimension: int = 1024
    milvus_metric_type: Literal["COSINE"] = "COSINE"
    embedding_mode: Literal["disabled", "openai_compatible"] = "disabled"
    embedding_base_url: str | None = None
    embedding_api_key: str | None = None
    embedding_model: str = "BAAI/bge-m3"
    embedding_dimension: int = 1024
    embedding_timeout_seconds: float = Field(default=15.0, gt=0)
    embedding_batch_size: int = Field(default=16, ge=1, le=128)
    rerank_mode: Literal["disabled", "http"] = "disabled"
    rerank_base_url: str | None = None
    rerank_api_key: str | None = None
    rerank_model: str = "BAAI/bge-reranker-v2-m3"
    rerank_timeout_seconds: float = Field(default=15.0, gt=0)
    rerank_top_n: int = Field(default=30, ge=1)
    manual_keyword_top_n: int = Field(default=20, ge=1)
    manual_vector_top_n: int = Field(default=20, ge=1)
    ticket_keyword_top_n: int = Field(default=20, ge=1)
    ticket_vector_top_n: int = Field(default=20, ge=1)
    rerank_input_size: int = Field(default=30, ge=1)
    manual_final_top_k: int = Field(default=5, ge=1)
    ticket_final_top_k: int = Field(default=5, ge=1)
    manual_similarity_threshold: float = Field(default=0.45, ge=0, le=1)
    ticket_similarity_threshold: float = Field(default=0.50, ge=0, le=1)
    semantic_dedup_threshold: float = Field(default=0.92, ge=0, le=1)
    max_chunks_per_document: int = Field(default=2, ge=1)
    max_results_per_ticket: int = Field(default=1, ge=1)
    retrieval_keyword_weight: float = Field(default=0.30, ge=0, le=1)
    retrieval_vector_weight: float = Field(default=0.40, ge=0, le=1)
    retrieval_rerank_weight: float = Field(default=0.30, ge=0, le=1)
    final_retrieval_weight: float = Field(default=0.35, ge=0, le=1)
    final_source_reliability_weight: float = Field(default=0.20, ge=0, le=1)
    final_verification_weight: float = Field(default=0.15, ge=0, le=1)
    final_relevance_to_alarm_weight: float = Field(default=0.15, ge=0, le=1)
    final_freshness_weight: float = Field(default=0.15, ge=0, le=1)
    document_max_bytes: int = Field(default=20 * 1024 * 1024, gt=0)

    @model_validator(mode="after")
    def validate_dependencies_and_weights(self) -> "Settings":
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
        if self.model_mode == "openai" and not self.openai_api_key:
            raise ValueError("OPENAI_API_KEY is required when MODEL_MODE=openai")
        if self.embedding_dimension != 1024 or self.milvus_vector_dimension != 1024:
            raise ValueError("BGE-M3 and Milvus vector dimensions must both be 1024")
        if self.retrieval_mode == "hybrid" and (
            self.embedding_mode != "openai_compatible"
            or not self.embedding_base_url
            or not self.embedding_api_key
        ):
            raise ValueError("Hybrid retrieval requires openai-compatible embedding credentials")
        if self.embedding_mode == "openai_compatible" and not (
            self.embedding_base_url and self.embedding_api_key
        ):
            raise ValueError("Embedding base URL and API key are required")
        if self.rerank_mode == "http" and not (self.rerank_base_url and self.rerank_api_key):
            raise ValueError("Reranker base URL and API key are required")
        groups = (
            (
                self.retrieval_keyword_weight,
                self.retrieval_vector_weight,
                self.retrieval_rerank_weight,
            ),
            (
                self.final_retrieval_weight,
                self.final_source_reliability_weight,
                self.final_verification_weight,
                self.final_relevance_to_alarm_weight,
                self.final_freshness_weight,
            ),
        )
        if any(abs(sum(group) - 1.0) > 1e-9 for group in groups):
            raise ValueError("Retrieval and final score weight groups must each sum to 1")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
