import json
import logging

from energy_agent.core.context import RequestContext, bind_context, reset_context
from energy_agent.core.ids import new_id
from energy_agent.observability.logging import ContextFormatter


def test_json_log_contains_context() -> None:
    context = RequestContext(trace_id=new_id(), request_id=new_id())
    token = bind_context(context)
    try:
        record = logging.LogRecord("test", logging.INFO, "", 0, "event", (), None)
        payload = json.loads(ContextFormatter(json_output=True).format(record))
    finally:
        reset_context(token)
    assert payload["trace_id"] == context.trace_id
    assert payload["request_id"] == context.request_id


def test_json_log_contains_span_fields_without_request_context() -> None:
    record = logging.LogRecord("test", logging.INFO, "", 0, "event", (), None)
    record.trace_id = new_id()
    record.span_name = "foundation"
    record.span_status = "ok"
    record.duration_ms = 12
    payload = json.loads(ContextFormatter(json_output=True).format(record))
    assert payload["trace_id"] == record.trace_id
    assert payload["span_name"] == "foundation"
    assert payload["span_status"] == "ok"
    assert payload["duration_ms"] == 12
