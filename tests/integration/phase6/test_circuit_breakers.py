import pytest

from energy_agent.reliability.circuit_breaker import CircuitBreaker, CircuitOpenError
from energy_agent.reliability.policies import CircuitBreakerPolicy

pytestmark = pytest.mark.integration


def test_dependency_failure_and_recovery() -> None:
    clock = [0.0]
    breaker = CircuitBreaker(
        "model",
        CircuitBreakerPolicy(failure_threshold=1, recovery_timeout_seconds=1),
        clock=lambda: clock[0],
    )
    breaker.record_failure()
    with pytest.raises(CircuitOpenError):
        breaker.allow()
    clock[0] = 2
    breaker.allow()
    breaker.record_success()
    breaker.allow()
