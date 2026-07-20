# Deployment runbook

1. Configure trusted headers, `INTERNAL_API_KEY`, Pilot actor allowlist, Redis rate
   limits, database credentials, model/RAG credentials, and LangFuse credentials.
2. Run `make verify-design`, `make phase6-check`, and review the generated evaluation
   report. Do not substitute image health for business acceptance.
3. Run migrations explicitly with `make migrate`; application startup never runs them.
4. Start the single-instance profile with `make up-phase6`. Start dashboards with
   `make up-pilot-observability`.
5. Verify `/health/live`, `/health/ready`, authenticated `/metrics`, one diagnosis per
   template, node-driven SSE, case review, indexing, graph degradation, and LangFuse.

RabbitMQ is used only for indexing. Neo4j is an optional enhancement and must not block
the diagnosis API.
