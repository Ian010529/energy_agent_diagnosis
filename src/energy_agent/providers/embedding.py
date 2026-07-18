import asyncio
import math
from time import monotonic

import httpx

from energy_agent.core.errors import (
    EmbeddingDimensionError,
    EmbeddingResponseError,
    EmbeddingUnavailableError,
)
from energy_agent.observability.logging import log_event


class OpenAICompatibleEmbeddingProvider:
    provider_type = "openai_compatible"

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        dimension: int,
        timeout_seconds: float,
        batch_size: int,
        max_retries: int = 2,
    ) -> None:
        self.model = model
        self.dimension = dimension
        self.batch_size = batch_size
        self.max_retries = max_retries
        self.client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout_seconds,
        )

    async def _batch(self, texts: list[str]) -> list[list[float]]:
        started = monotonic()
        for attempt in range(1, self.max_retries + 2):
            try:
                response = await self.client.post(
                    "/v1/embeddings",
                    json={"model": self.model, "input": [text[:16_000] for text in texts]},
                )
                if response.status_code == 429 or response.status_code >= 500:
                    raise EmbeddingUnavailableError(f"Embedding HTTP {response.status_code}")
                response.raise_for_status()
                data = response.json().get("data")
                if not isinstance(data, list) or len(data) != len(texts):
                    raise EmbeddingResponseError("Embedding response count mismatch")
                ordered = sorted(data, key=lambda item: int(item.get("index", 0)))
                vectors = [item.get("embedding") for item in ordered]
                if any(not isinstance(vector, list) for vector in vectors):
                    raise EmbeddingResponseError("Embedding response is missing vectors")
                typed = [[float(value) for value in vector] for vector in vectors]
                if any(len(vector) != self.dimension for vector in typed):
                    raise EmbeddingDimensionError("Embedding dimension mismatch")
                if any(not math.isfinite(value) for vector in typed for value in vector):
                    raise EmbeddingResponseError("Embedding contains non-finite values")
                log_event(
                    __import__("logging").getLogger(__name__),
                    20,
                    "embedding_completed",
                    model=self.model,
                    batch_size=len(texts),
                    vector_dimension=self.dimension,
                    latency_ms=int((monotonic() - started) * 1000),
                    attempt=attempt,
                )
                return typed
            except (httpx.TimeoutException, httpx.NetworkError, EmbeddingUnavailableError) as exc:
                if attempt > self.max_retries:
                    raise EmbeddingUnavailableError("Embedding provider unavailable") from exc
                await asyncio.sleep(0.05 * attempt)
        raise EmbeddingUnavailableError("Embedding provider unavailable")

    async def embed(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self.batch_size):
            vectors.extend(await self._batch(texts[start : start + self.batch_size]))
        return vectors

    async def health(self) -> bool:
        return len((await self.embed(["health"]))[0]) == self.dimension

    async def close(self) -> None:
        await self.client.aclose()
