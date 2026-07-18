import json
from typing import Any

import httpx
from pydantic import BaseModel, ValidationError

from energy_agent.agent.state import CandidateCause, ClarificationQuestion
from energy_agent.contracts.common import StrictModel
from energy_agent.observability.tracing import Tracer


class CandidateCauseEnvelope(StrictModel):
    candidate_causes: list[CandidateCause]


class ClarificationEnvelope(StrictModel):
    clarification_questions: list[ClarificationQuestion]


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
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.temperature = temperature
        self.tracer = tracer

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
        with self.tracer.start_generation(
            f"llm.{node_name}",
            trace_id=trace_id,
            model=self.model,
            metadata={"prompt_version": prompt_version, "provider": "openai_compatible"},
        ) as generation:
            try:
                async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                    response = await client.post(
                        f"{self.base_url}/v1/chat/completions",
                        headers={
                            "Authorization": f"Bearer {self.api_key}",
                            "X-Trace-Id": trace_id,
                            "X-Session-Id": session_id,
                            "X-Prompt-Version": prompt_version,
                        },
                        json={
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
                        },
                    )
                    response.raise_for_status()
                body: dict[str, Any] = response.json()
                content = body["choices"][0]["message"]["content"]
                validated = output_schema.model_validate_json(content)
                generation.set_output(
                    {
                        "finish_reason": body["choices"][0].get("finish_reason"),
                        "usage": body.get("usage", {}),
                        "validated": True,
                    }
                )
                return validated
            except (httpx.HTTPError, KeyError, TypeError, ValidationError, ValueError) as exc:
                generation.record_event(
                    "model_fallback",
                    {"error_code": type(exc).__name__, "prompt_version": prompt_version},
                )
                return None
