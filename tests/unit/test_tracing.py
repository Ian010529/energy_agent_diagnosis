import logging
from contextlib import nullcontext
from hashlib import sha256

from energy_agent.core.ids import new_id
from energy_agent.observability.langfuse import LangFuseTracer
from energy_agent.observability.tracing import LocalTracer


class FailingClient:
    def start_as_current_observation(self, **kwargs):
        raise RuntimeError("offline")

    def flush(self):
        raise RuntimeError("offline")

    def shutdown(self):
        raise RuntimeError("offline")


class RecordingClient:
    def __init__(self) -> None:
        self.kwargs = {}

    def start_as_current_observation(self, **kwargs):
        self.kwargs = kwargs
        return nullcontext(None)

    def flush(self):
        return None

    def shutdown(self):
        return None


def tracer(client):
    return LangFuseTracer(
        public_key="public",
        secret_key="secret",
        host="https://example.invalid",
        environment="test",
        client=client,
    )


def test_local_tracer_records_span(caplog) -> None:
    caplog.set_level(logging.INFO)
    local = LocalTracer()
    with local.start_span("foundation", trace_id=new_id()) as span:
        span.set_output({"ok": True})
    assert "trace_span_finished" in caplog.text


async def test_langfuse_failure_does_not_escape(caplog) -> None:
    remote = tracer(FailingClient())
    with remote.start_span("foundation", trace_id=new_id()) as span:
        span.set_output({"password": "hidden"})
    await remote.flush()
    await remote.shutdown()
    assert "trace_export_failed" in caplog.text
    assert remote.export_failed is True


def test_langfuse_redacts_metadata() -> None:
    client = RecordingClient()
    remote = tracer(client)
    with remote.start_span(
        "foundation",
        trace_id=new_id(),
        metadata={"password": "hidden"},
    ):
        pass
    assert client.kwargs["metadata"]["password"] == "[REDACTED]"


def test_langfuse_normalizes_uuid_and_business_trace_ids() -> None:
    client = RecordingClient()
    remote = tracer(client)
    uuid_trace_id = "12345678-1234-5678-1234-567812345678"
    with remote.start_span("foundation", trace_id=uuid_trace_id):
        pass
    assert client.kwargs["trace_context"]["trace_id"] == uuid_trace_id.replace("-", "")

    business_trace_id = "graph-template-pcs_temperature_abnormal_v1"
    with remote.start_span("foundation", trace_id=business_trace_id):
        pass
    assert (
        client.kwargs["trace_context"]["trace_id"]
        == sha256(business_trace_id.encode("utf-8")).hexdigest()[:32]
    )
