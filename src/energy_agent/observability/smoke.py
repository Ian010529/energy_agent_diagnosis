import asyncio
import os

from energy_agent.core.ids import new_id
from energy_agent.observability.langfuse import LangFuseTracer


async def main() -> int:
    public_key = os.getenv("LANGFUSE_PUBLIC_KEY")
    secret_key = os.getenv("LANGFUSE_SECRET_KEY")
    if not public_key or not secret_key:
        print("LANGFUSE_LIVE_VALIDATION=BLOCKED_MISSING_CREDENTIALS")
        return 2
    tracer = LangFuseTracer(
        public_key=public_key,
        secret_key=secret_key,
        host=os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com"),
        environment=os.getenv("APP_ENV", "local"),
    )
    trace_id = new_id()
    with tracer.start_trace(
        "phase1.foundation.observability_smoke",
        trace_id=trace_id,
        metadata={"phase": "phase1", "kind": "connectivity"},
    ) as span:
        span.record_event("phase1.smoke.span", {"test": True})
        span.set_output({"status": "sent"})
    await tracer.flush()
    await tracer.shutdown()
    print(f"LANGFUSE_LIVE_VALIDATION=ATTEMPTED trace_id={trace_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
