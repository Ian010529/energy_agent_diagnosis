from energy_agent.core.context import (
    RequestContext,
    bind_context,
    get_context,
    reset_context,
)
from energy_agent.core.ids import new_id, trusted_or_new_id, valid_id


def test_uuid_ids_are_valid_and_untrusted_values_are_replaced() -> None:
    generated = new_id()
    assert valid_id(generated)
    assert trusted_or_new_id(generated) == generated
    assert trusted_or_new_id("not-a-uuid") != "not-a-uuid"


def test_context_can_be_bound_and_cleaned() -> None:
    context = RequestContext(trace_id=new_id(), request_id=new_id())
    token = bind_context(context)
    assert get_context() == context
    reset_context(token)
    assert get_context() is None
