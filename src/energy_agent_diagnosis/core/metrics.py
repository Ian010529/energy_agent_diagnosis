"""提供低基数的 HTTP、异常和依赖健康 Prometheus 指标。"""

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, generate_latest


class Metrics:
    """为单个 FastAPI 应用实例持有独立指标注册表。"""

    def __init__(self, namespace: str) -> None:
        """创建阶段 1 需要的基础指标，避免测试实例互相注册冲突。"""
        self.registry = CollectorRegistry(auto_describe=True)
        self.request_count = Counter(
            "http_requests_total",
            "HTTP 请求总数",
            ("method", "route", "status"),
            namespace=namespace,
            registry=self.registry,
        )
        self.request_duration = Histogram(
            "http_request_duration_seconds",
            "HTTP 请求耗时",
            ("method", "route"),
            namespace=namespace,
            registry=self.registry,
        )
        self.exception_count = Counter(
            "http_exceptions_total",
            "未处理 HTTP 异常总数",
            ("method", "route", "exception_type"),
            namespace=namespace,
            registry=self.registry,
        )
        self.dependency_health = Gauge(
            "dependency_health",
            "依赖健康状态：健康为 1，异常为 0",
            ("dependency", "required"),
            namespace=namespace,
            registry=self.registry,
        )

    def render(self) -> bytes:
        """把当前注册表编码为 Prometheus 文本格式。"""
        return generate_latest(self.registry)

    def set_dependency_health(self, name: str, *, required: bool, healthy: bool) -> None:
        """更新有限依赖集合的健康状态，不使用 Trace 等高基数标签。"""
        self.dependency_health.labels(name, str(required).lower()).set(1 if healthy else 0)
