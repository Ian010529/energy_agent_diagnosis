# Security checklist

- JWT or trusted-header mode plus the internal key is mandatory outside local/test.
- JWT algorithms, issuer, audiences, expiration, type, user status, role, and token
  version are verified; access and refresh secrets are distinct.
- Access and refresh tokens use HttpOnly, SameSite=Strict cookies. Tokens are absent
  from browser JavaScript, local/session storage, URLs, logs, traces, and audit.
- Refresh sessions store SHA-256 token digests only; rotation and reuse-family
  revocation are enabled.
- Passwords use Argon2id and are absent from logs/audit; password hashes are never
  returned by APIs.
- Cookie-authenticated writes enforce exact Origin/Host same-origin checks.
- Service actors cannot be forged through external actor headers.
- Pilot writers are explicitly allowlisted; admin has no bypass.
- Redis rate-limit keys contain only actor hashes and Pilot writes fail closed.
- Request limits, exact CORS allowlist, no-store/nosniff/referrer headers are enabled.
- Metrics require internal authentication and expose no business payload.
- `.env`, Gold, source manuals, Git history, and test dependencies are absent from the
  production image; the process runs as non-root.
- `make dependency-audit` and `make static-security-check` have no unresolved severe
  finding. Logs and traces contain no auth headers, DSNs, tokens, or raw long content.
