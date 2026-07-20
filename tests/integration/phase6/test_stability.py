import pytest

from energy_agent.reliability.circuit_breaker import CircuitBreaker

pytestmark = pytest.mark.integration


def test_small_controlled_recovery_loop_does_not_accumulate_failures() -> None:
    breaker = CircuitBreaker("neo4j")
    for _ in range(20):
        breaker.allow()
        breaker.record_success()
    assert breaker.failure_count == 0
