from collections.abc import Callable
from time import monotonic

from energy_agent.observability.metrics import CIRCUIT_BREAKER_STATE
from energy_agent.reliability.contracts import BreakerSnapshot, CircuitState
from energy_agent.reliability.policies import CircuitBreakerPolicy


class CircuitOpenError(RuntimeError):
    pass


class CircuitBreaker:
    def __init__(
        self,
        dependency: str,
        policy: CircuitBreakerPolicy | None = None,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        self.dependency = dependency
        self.policy = policy or CircuitBreakerPolicy()
        self.clock = clock
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.opened_at: float | None = None
        self._half_open_probe_active = False
        self._publish_state()

    def _publish_state(self) -> None:
        value = {
            CircuitState.CLOSED: 0.0,
            CircuitState.HALF_OPEN: 0.5,
            CircuitState.OPEN: 1.0,
        }[self.state]
        CIRCUIT_BREAKER_STATE.labels(dependency=self.dependency).set(value)

    def allow(self) -> None:
        if self.state == CircuitState.CLOSED:
            return
        if self.state == CircuitState.OPEN:
            if self.opened_at is None:
                self.opened_at = self.clock()
            if self.clock() - self.opened_at < self.policy.recovery_timeout_seconds:
                raise CircuitOpenError(f"{self.dependency} circuit is open")
            self.state = CircuitState.HALF_OPEN
            self._publish_state()
            self._half_open_probe_active = False
        if self._half_open_probe_active:
            raise CircuitOpenError(f"{self.dependency} half-open probe is active")
        self._half_open_probe_active = True

    def record_success(self) -> None:
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.opened_at = None
        self._half_open_probe_active = False
        self._publish_state()

    def record_failure(self, *, countable: bool = True) -> None:
        if not countable:
            self._half_open_probe_active = False
            return
        self.failure_count += 1
        if (
            self.state == CircuitState.HALF_OPEN
            or self.failure_count >= self.policy.failure_threshold
        ):
            self.state = CircuitState.OPEN
            self.opened_at = self.clock()
        self._half_open_probe_active = False
        self._publish_state()

    def snapshot(self) -> BreakerSnapshot:
        return BreakerSnapshot(
            dependency=self.dependency,
            state=self.state,
            failure_count=self.failure_count,
            opened_at=self.opened_at,
        )
