# Rollback runbook

Stop new Pilot writes, retain audit/step logs and outbox rows, and record the affected
release and evaluation run. Roll back the application image first. Downgrade migration
`0006_phase6` only after exporting Phase 6 action, Guardrail, and dedup data and
confirming no rollback consumer depends on it. Never delete loaded Phase 1–5 data.
Re-enable traffic only after five-template smoke, SSE persistence, and metrics checks.
