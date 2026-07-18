from pydantic import Field

from energy_agent.contracts.common import StrictModel


class ErrorBody(StrictModel):
    code: str
    message: str
    retryable: bool = False
    details: dict[str, object] = Field(default_factory=dict)


class ErrorEnvelope(StrictModel):
    error: ErrorBody
    trace_id: str
