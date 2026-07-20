# Evaluation guide

Evaluation uses the public API only: create a session, submit a message, execute the
shared LangGraph and tools, persist state, and query the final result. Gold is loaded
only by the evaluation process and never sent to the API, Redis, MySQL business tables,
Milvus, Neo4j, prompts, or LangFuse.

Calibration (100) validates the evaluator. Regression (100) supports comparisons.
Holdout (50) is reserved for the final `pilot-gate` and cannot drive prompt, rule,
template, threshold, or Gold changes. Reports disclose the active dataset validation
status and separate split, template, evidence-profile, manual sensitivity, conflict,
and weak-only results. Baselines change only through the explicit `accept-baseline` CLI.

For dataset replacement in the dedicated synthetic environment, run
`make reload-pilot-data REPLACE_ALL=1`, then `make drain-pilot-index` and
`make validate-pilot-manual-vectors`. The replacement command is destructive and is
not part of normal CI. System-level evaluation concurrency must not exceed
`RATE_LIMIT_STREAM_CONCURRENT`; a rejected or failed sample is recorded as `FAILED`
instead of discarding the rest of the evaluation run.
