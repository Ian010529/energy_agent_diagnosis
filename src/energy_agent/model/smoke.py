import asyncio

from energy_agent.core.config import Settings
from energy_agent.model.gateway import ModelGateway
from energy_agent.observability.tracing import LocalTracer
from energy_agent.retrieval.contracts import QueryRewrite


async def _run() -> None:
    settings = Settings()
    if settings.model_mode != "openai" or not settings.openai_api_key:
        print("MODEL_GATEWAY_VALIDATION=BLOCKED_MISSING_CREDENTIALS")
        return
    gateway = ModelGateway(
        base_url=settings.openai_base_url,
        api_key=settings.openai_api_key,
        model=settings.model_name,
        timeout_seconds=settings.model_timeout_seconds,
        temperature=settings.model_temperature,
        tracer=LocalTracer(),
        api_mode="responses",
    )
    result = await gateway.generate(
        trace_id="phase3-model-smoke",
        session_id="phase3-model-smoke",
        node_name="query_rewrite",
        prompt_version="rag.query_rewrite.v1.0",
        system_prompt=(
            "Return a concise retrieval query rewrite. Preserve the alarm and equipment "
            "identifiers. Fill every field in the supplied JSON schema."
        ),
        evidence_package={
            "query": "PCS 温度告警怎么处理",
            "alarm_name": "温度告警",
            "device_type": "PCS",
            "device_model": "SC5000",
        },
        output_schema=QueryRewrite,
    )
    if result is None:
        raise SystemExit("MODEL_GATEWAY_VALIDATION=FAILED")
    rewrite = QueryRewrite.model_validate(result)
    print(
        "MODEL_GATEWAY_VALIDATION=PASSED "
        f"model={settings.model_name} rewrite_version={rewrite.rewrite_version}"
    )


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
