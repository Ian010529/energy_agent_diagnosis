# Configuration reference

Pilot requires `APP_ENV=pilot`, `AUTH_MODE=trusted_headers`, a non-empty
`INTERNAL_API_KEY`, `PILOT_MODE=true`, and comma-separated `PILOT_ALLOWED_ACTORS`.
Enable Redis controls with `RATE_LIMIT_ENABLED=true`; configure diagnosis, review,
case-write, and stream limits separately. `CORS_ALLOW_ORIGINS` is a comma-separated
exact allowlist. `REQUEST_BODY_MAX_BYTES` caps write request bodies.

Set `GRAPH_MODE=disabled` to remove Neo4j enhancement. Set
`RETRIEVAL_MODE=keyword_only`, `EMBEDDING_MODE=disabled`, and `RERANK_MODE=disabled`
for an explicit lexical fallback. Set `MODEL_MODE=disabled` for rule/template output.
Never store allowlists, keys, DSNs, or tokens in Git or logs.
