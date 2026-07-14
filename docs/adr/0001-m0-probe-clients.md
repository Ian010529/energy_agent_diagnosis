# ADR 0001: M0 infrastructure probe clients

- Status: Accepted
- Date: 2026-07-15
- Scope: M0 test tooling only

## Decision

M0 uses each infrastructure vendor's production network protocol through pinned
Python clients in the `dev` dependency group. The runtime project has no
production dependencies and no provider implementation in M0.

## Reason

Health endpoints cannot prove authenticated writes, publisher confirmation,
persistence, or authoritative readback. The probe clients perform those checks
against the same services and protocols that later modules will use. They are
excluded from runtime images until a later module explicitly adopts them.
