import json
from copy import deepcopy
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
        api_mode: str = "chat_completions",
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.temperature = temperature
        self.tracer = tracer
        self.api_mode = api_mode

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
                    schema = _openai_strict_schema(output_schema.model_json_schema())
                    payload = (
                        {
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
                            "reasoning": {"effort": "low"},
                            "max_output_tokens": 2048,
                        }
                        if self.api_mode == "responses"
                        else {
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
                    )
                    endpoint = (
                        "/v1/responses" if self.api_mode == "responses" else "/v1/chat/completions"
                    )
                    response = await client.post(
                        f"{self.base_url}{endpoint}",
                        headers={
                            "Authorization": f"Bearer {self.api_key}",
                            "X-Trace-Id": trace_id,
                            "X-Session-Id": session_id,
                            "X-Prompt-Version": prompt_version,
                        },
                        json=payload,
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
                return validated
            except (httpx.HTTPError, KeyError, TypeError, ValidationError, ValueError) as exc:
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
