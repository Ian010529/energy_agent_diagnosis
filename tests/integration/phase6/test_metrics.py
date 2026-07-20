import pytest
from prometheus_client import generate_latest

from energy_agent.observability.metrics import HTTP_REQUESTS

pytestmark = pytest.mark.integration


def test_prometheus_scrape_has_phase6_metrics_without_high_cardinality_labels() -> None:
    HTTP_REQUESTS.labels(method="GET", route="/health/live", status="200").inc()
    payload = generate_latest().decode()
    assert "energy_http_requests_total" in payload
    assert "session_id=" not in payload
    assert "trace_id=" not in payload
