from energy_agent.reliability.circuit_breaker import CircuitBreaker
from energy_agent.reliability.policies import DEPENDENCIES, CircuitBreakerPolicy


class CircuitBreakerRegistry:
    def __init__(self, policy: CircuitBreakerPolicy | None = None) -> None:
        self._breakers = {name: CircuitBreaker(name, policy=policy) for name in DEPENDENCIES}

    def get(self, dependency: str) -> CircuitBreaker:
        try:
            return self._breakers[dependency]
        except KeyError as exc:
            raise ValueError(f"Unsupported circuit dependency: {dependency}") from exc

    def snapshots(self) -> dict[str, object]:
        return {
            name: breaker.snapshot().model_dump(mode="json")
            for name, breaker in sorted(self._breakers.items())
        }
