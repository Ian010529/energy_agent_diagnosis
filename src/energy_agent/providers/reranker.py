import asyncio

import httpx

from energy_agent.core.errors import RerankerResponseError, RerankerUnavailableError
from energy_agent.reliability.circuit_breaker import CircuitBreaker, CircuitOpenError


class HttpRerankerProvider:
    provider_type = "http"

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: float,
        max_retries: int = 2,
        circuit_breaker: CircuitBreaker | None = None,
    ) -> None:
        self.model = model
        self.max_retries = max_retries
        self.circuit_breaker = circuit_breaker
        self.client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout_seconds,
        )

    async def rerank(self, query: str, candidates: list[tuple[str, str]]) -> dict[str, float]:
        ids = [identifier for identifier, _ in candidates]
        if self.circuit_breaker:
            try:
                self.circuit_breaker.allow()
            except CircuitOpenError as exc:
                raise RerankerUnavailableError("Reranker circuit is open") from exc
        for attempt in range(1, self.max_retries + 2):
            try:
                response = await self.client.post(
                    "/v1/rerank",
                    json={
                        "model": self.model,
                        "query": query[:8_000],
                        "documents": [text[:8_000] for _, text in candidates],
                    },
                )
                if response.status_code == 429 or response.status_code >= 500:
                    raise RerankerUnavailableError(f"Reranker HTTP {response.status_code}")
                response.raise_for_status()
                results = response.json().get("results")
                if not isinstance(results, list) or len(results) != len(candidates):
                    raise RerankerResponseError("Reranker result count mismatch")
                output: dict[str, float] = {}
                for result in results:
                    index = result.get("index")
                    score = result.get("relevance_score", result.get("score"))
                    if (
                        not isinstance(index, int)
                        or index >= len(ids)
                        or not isinstance(score, (int, float))
                    ):
                        raise RerankerResponseError("Invalid reranker result")
                    output[ids[index]] = max(0.0, min(1.0, float(score)))
                if set(output) != set(ids):
                    raise RerankerResponseError("Reranker candidate IDs do not align")
                if self.circuit_breaker:
                    self.circuit_breaker.record_success()
                return output
            except (httpx.TimeoutException, httpx.NetworkError, RerankerUnavailableError) as exc:
                if attempt > self.max_retries:
                    if self.circuit_breaker:
                        self.circuit_breaker.record_failure()
                    raise RerankerUnavailableError("Reranker unavailable") from exc
                await asyncio.sleep(0.05 * attempt)
            except RerankerResponseError:
                if self.circuit_breaker:
                    self.circuit_breaker.record_failure(countable=False)
                raise
        raise RerankerUnavailableError("Reranker unavailable")

    async def close(self) -> None:
        await self.client.aclose()

    async def health(self) -> bool:
        scores = await self.rerank("temperature alarm", [("health", "temperature alarm")])
        return "health" in scores
