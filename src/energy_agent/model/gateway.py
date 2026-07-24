import asyncio
import json
from copy import deepcopy
from time import monotonic
from typing import Any

import httpx
from pydantic import BaseModel, ValidationError

from energy_agent.model.contracts import CandidateCauseEnvelope, ClarificationEnvelope
from energy_agent.observability.metrics import MODEL_CALLS, MODEL_DURATION, MODEL_TOKENS
from energy_agent.observability.tracing import Tracer
from energy_agent.reliability.circuit_breaker import CircuitBreaker, CircuitOpenError

__all__ = ["CandidateCauseEnvelope", "ClarificationEnvelope", "ModelGateway"]


class ModelGateway:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: float,
        temperature: float,
        tracer: Tracer,
        api_mode: str = "chat_completions",
        circuit_breaker: CircuitBreaker | None = None,
        max_retries: int = 2,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.temperature = temperature
        self.tracer = tracer
        self.api_mode = api_mode
        self.circuit_breaker = circuit_breaker
        self.max_retries = max_retries

    async def _post_with_retry(
        self,
        client: httpx.AsyncClient,
        endpoint: str,
        *,
        headers: dict[str, str],
        payload: dict[str, object],
    ) -> httpx.Response:
        for attempt in range(self.max_retries + 1):
            try:
                response = await client.post(
                    f"{self.base_url}{endpoint}",
                    headers=headers,
                    json=payload,
                )
            except (httpx.TimeoutException, httpx.NetworkError):
                if attempt >= self.max_retries:
                    raise
                await asyncio.sleep(0.1 * (attempt + 1))
                continue
            if (
                response.status_code == 429 or response.status_code >= 500
            ) and attempt < self.max_retries:
                await asyncio.sleep(0.1 * (attempt + 1))
                continue
            return response
        raise RuntimeError("Model request retry loop exhausted")

    async def generate(
        self,
        *,
        trace_id: str,
        session_id: str,
        node_name: str,
        prompt_version: str,
        system_prompt: str,
        evidence_package: dict[str, object],
        output_schema: type[BaseModel],
    ) -> BaseModel | None:
        started = monotonic()
        if self.circuit_breaker:
            try:
                self.circuit_breaker.allow()
            except CircuitOpenError:
                MODEL_CALLS.labels(provider="openai_compatible", status="circuit_open").inc()
                return None
        with self.tracer.start_generation(
            f"llm.{node_name}",
            trace_id=trace_id,
            model=self.model,
            metadata={"prompt_version": prompt_version, "provider": "openai_compatible"},
        ) as generation:
            try:
                async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                    schema = _openai_strict_schema(output_schema.model_json_schema())
                    if self.api_mode == "responses":
                        payload: dict[str, object] = {
                            "model": self.model,
                            "instructions": system_prompt,
                            "input": json.dumps(evidence_package, ensure_ascii=False, default=str),
                            "text": {
                                "format": {
                                    "type": "json_schema",
                                    "name": output_schema.__name__,
                                    "strict": True,
                                    "schema": schema,
                                }
                            },
                            "max_output_tokens": 2048,
                        }
                        if _supports_reasoning_effort(self.model):
                            payload["reasoning"] = {"effort": "low"}
                    else:
                        payload = {
                            "model": self.model,
                            "messages": [
                                {"role": "system", "content": system_prompt},
                                {
                                    "role": "user",
                                    "content": json.dumps(
                                        evidence_package, ensure_ascii=False, default=str
                                    ),
                                },
                            ],
                            "temperature": self.temperature,
                            "response_format": {"type": "json_object"},
                        }
                    endpoint = (
                        "/v1/responses" if self.api_mode == "responses" else "/v1/chat/completions"
                    )
                    response = await self._post_with_retry(
                        client,
                        endpoint,
                        headers={
                            "Authorization": f"Bearer {self.api_key}",
                            "X-Trace-Id": trace_id,
                            "X-Session-Id": session_id,
                            "X-Prompt-Version": prompt_version,
                        },
                        payload=payload,
                    )
                    response.raise_for_status()
                body: dict[str, Any] = response.json()
                if self.api_mode == "responses":
                    output_texts = [
                        item["text"]
                        for output in body["output"]
                        for item in output.get("content", [])
                        if item.get("type") == "output_text"
                    ]
                    if not output_texts:
                        raise ValueError("OpenAI Responses payload has no output_text")
                    content = output_texts[0]
                    finish_reason = body.get("status")
                else:
                    content = body["choices"][0]["message"]["content"]
                    finish_reason = body["choices"][0].get("finish_reason")
                validated = output_schema.model_validate_json(content)
                generation.set_output(
                    {
                        "finish_reason": finish_reason,
                        "usage": body.get("usage", {}),
                        "validated": True,
                    }
                )
                if self.circuit_breaker:
                    self.circuit_breaker.record_success()
                MODEL_CALLS.labels(provider="openai_compatible", status="ok").inc()
                MODEL_DURATION.labels(provider="openai_compatible", status="ok").observe(
                    monotonic() - started
                )
                usage = body.get("usage", {})
                if isinstance(usage, dict):
                    MODEL_TOKENS.labels(provider="openai_compatible", direction="input").inc(
                        int(usage.get("input_tokens", usage.get("prompt_tokens", 0)) or 0)
                    )
                    MODEL_TOKENS.labels(provider="openai_compatible", direction="output").inc(
                        int(usage.get("output_tokens", usage.get("completion_tokens", 0)) or 0)
                    )
                return validated
            except (httpx.HTTPError, KeyError, TypeError, ValidationError, ValueError) as exc:
                if self.circuit_breaker:
                    self.circuit_breaker.record_failure(countable=isinstance(exc, httpx.HTTPError))
                MODEL_CALLS.labels(provider="openai_compatible", status="fallback").inc()
                MODEL_DURATION.labels(provider="openai_compatible", status="fallback").observe(
                    monotonic() - started
                )
                generation.record_event(
                    "model_fallback",
                    {"error_code": type(exc).__name__, "prompt_version": prompt_version},
                )
                return None


def _openai_strict_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Convert a Pydantic schema to the strict object shape required by Responses."""
    strict = deepcopy(schema)

    def visit(node: object) -> None:
        if isinstance(node, dict):
            properties = node.get("properties")
            if isinstance(properties, dict):
                node["required"] = list(properties)
                node["additionalProperties"] = False
            node.pop("default", None)
            for value in node.values():
                visit(value)
        elif isinstance(node, list):
            for value in node:
                visit(value)

    visit(strict)
    return strict


def _supports_reasoning_effort(model: str) -> bool:
    normalized = model.lower()
    return normalized.startswith(("gpt-5", "o1", "o3", "o4"))
