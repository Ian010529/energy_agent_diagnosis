# Incident runbook

Identify the failing dependency from health, metrics, structured logs, and LangFuse
without copying secrets or complete work orders into tickets. Apply the documented
degradation, verify warnings and `degraded_components`, and route unsafe or
multi-channel failures to a human. For indexing DLQ, stop retry loops, inspect the
sanitized error code, repair the dependency, then requeue through the supported index
workflow. Preserve audit and outbox records. Roll back when a technical safety gate,
migration integrity, or data durability condition fails.
