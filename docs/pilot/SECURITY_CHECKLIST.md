# Security checklist

- Trusted-header mode and internal key are mandatory outside local/test.
- Service actors cannot be forged through external actor headers.
- Pilot writers are explicitly allowlisted; admin has no bypass.
- Redis rate-limit keys contain only actor hashes and Pilot writes fail closed.
- Request limits, exact CORS allowlist, no-store/nosniff/referrer headers are enabled.
- Metrics require internal authentication and expose no business payload.
- `.env`, Gold, source manuals, Git history, and test dependencies are absent from the
  production image; the process runs as non-root.
- `make dependency-audit` and `make static-security-check` have no unresolved severe
  finding. Logs and traces contain no auth headers, DSNs, tokens, or raw long content.
