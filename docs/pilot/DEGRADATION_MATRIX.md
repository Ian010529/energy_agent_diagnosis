# Degradation matrix

| Failure | Required behavior |
|---|---|
| Model | Rule generation and template output |
| Embedding or Milvus | Keyword-only retrieval |
| Reranker | Simplified deterministic ranking |
| InfluxDB | `NEED_USER_INPUT`; no strong time-series conclusion |
| Neo4j | Remove graph enhancement and continue |
| RabbitMQ | Retain outbox; diagnosis continues |
| LangFuse | Continue structured logging |
| Multiple knowledge channels | Human takeover |
| All critical tools | Explicit failure or human takeover |

Every fallback must be visible in warnings, degraded components, traces, and metrics.
A fallback must never be reported as full success.
