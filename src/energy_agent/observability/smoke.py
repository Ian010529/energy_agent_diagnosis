import asyncio

from energy_agent.core.config import Settings
from energy_agent.core.ids import new_id
from energy_agent.observability.langfuse import LangFuseTracer


async def main() -> int:
    settings = Settings()
    if not settings.langfuse_public_key or not settings.langfuse_secret_key:
        print("LANGFUSE_LIVE_VALIDATION=BLOCKED_MISSING_CREDENTIALS")
        return 2
    tracer = LangFuseTracer(
        public_key=settings.langfuse_public_key,
        secret_key=settings.langfuse_secret_key,
        host=settings.langfuse_host,
        environment=settings.app_env,
        mode=settings.trace_content_mode,
        shutdown_timeout_seconds=15.0,
    )
    authenticated = False
    auth_checked = False
    for attempt in range(3):
        try:
            authenticated = await asyncio.to_thread(tracer.client.auth_check)
            auth_checked = True
            break
        except Exception:
            if attempt == 2:
                break
            await asyncio.sleep(0.5 * (attempt + 1))
    if not auth_checked:
        print("LANGFUSE_LIVE_VALIDATION=FAILED_CONNECTIVITY")
        await tracer.shutdown()
        return 1
    if not authenticated:
        print("LANGFUSE_LIVE_VALIDATION=FAILED_AUTH")
        await tracer.shutdown()
        return 1
    trace_id = new_id()
    with tracer.start_trace(
        "phase1.foundation.observability_smoke",
        trace_id=trace_id,
        metadata={"phase": "phase1", "kind": "connectivity"},
    ) as span:
        span.record_event("phase1.smoke.span", {"test": True})
        span.set_output({"status": "sent"})
    await tracer.flush()
    if tracer.export_failed:
        print("LANGFUSE_LIVE_VALIDATION=FAILED_EXPORT")
        await tracer.shutdown()
        return 1
    await tracer.shutdown()
    if tracer.export_failed:
        print("LANGFUSE_LIVE_VALIDATION=FAILED_SHUTDOWN")
        return 1
    print(f"LANGFUSE_LIVE_VALIDATION=PASSED trace_id={trace_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
