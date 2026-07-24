# Configuration reference

Pilot JWT login requires `APP_ENV=pilot`, `AUTH_MODE=jwt`,
`FRONTEND_AUTH_MODE=jwt`, a non-empty `INTERNAL_API_KEY`, distinct random
`JWT_ACCESS_SECRET` and `JWT_REFRESH_SECRET` values of at least 32 bytes,
`AUTH_COOKIE_SECURE=true`, `PILOT_MODE=true`, and comma-separated
`PILOT_ALLOWED_ACTORS` containing user IDs. `trusted_headers` remains supported for
an existing trusted gateway deployment.
Enable Redis controls with `RATE_LIMIT_ENABLED=true`; configure diagnosis, review,
case-write, and stream limits separately. `CORS_ALLOW_ORIGINS` is a comma-separated
exact allowlist. `REQUEST_BODY_MAX_BYTES` caps write request bodies.

Set `GRAPH_MODE=disabled` to remove Neo4j enhancement. Set
`RETRIEVAL_MODE=keyword_only`, `EMBEDDING_MODE=disabled`, and `RERANK_MODE=disabled`
for an explicit lexical fallback. Set `MODEL_MODE=disabled` for rule/template output.
Never store allowlists, keys, DSNs, or tokens in Git or logs.

JWT defaults are issuer `energy-agent`, access audience `energy-agent-api`, refresh
audience `energy-agent-refresh`, access TTL 15 minutes, and refresh TTL 7 days.
Bootstrap credentials are supplied temporarily through
`BOOTSTRAP_ADMIN_USERNAME`, `BOOTSTRAP_ADMIN_PASSWORD`,
`BOOTSTRAP_ADMIN_DISPLAY_NAME`, and optional `BOOTSTRAP_ADMIN_EMAIL`; remove the
password from the environment after `make bootstrap-admin`.
