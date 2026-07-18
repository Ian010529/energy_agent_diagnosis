# Energy Agent Diagnosis

Phase 1 provides the modular FastAPI foundation, control-plane persistence, short-term
Redis memory, structured logging, redaction, and local/LangFuse tracing boundaries. It
does not expose a diagnosis API or return diagnostic conclusions.

## Local verification

```bash
uv sync
make up-core
make migrate
make phase1-check
```

Run the application with:

```bash
uv run uvicorn energy_agent.app:app --reload
```

The foundation endpoints are `GET /health/live` and `GET /health/ready`.

LangFuse connectivity is an explicit, non-default check:

```bash
make smoke-langfuse
```

Without `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY`, it reports
`LANGFUSE_LIVE_VALIDATION=BLOCKED_MISSING_CREDENTIALS`.
