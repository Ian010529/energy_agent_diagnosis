from dataclasses import dataclass


@dataclass(frozen=True)
class CircuitBreakerPolicy:
    failure_threshold: int = 3
    recovery_timeout_seconds: float = 30.0


DEPENDENCIES = frozenset(
    {"model", "influxdb", "embedding", "milvus", "reranker", "neo4j", "rabbitmq"}
)
