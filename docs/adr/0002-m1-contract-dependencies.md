# ADR 0002: M1 contract and canonicalization dependencies

- Status: Accepted
- Date: 2026-07-15
- Scope: M1 shared contracts and tests

## Decision

M1 declares Pydantic v2 as a production dependency for every cross-boundary DTO
and the typed configuration boundary. Hypothesis is added only to the development
dependency group for canonicalization property tests.

The M1 migration and live-gate tooling continues to use the PyMySQL and Redis
clients accepted for development tooling by ADR 0001. M1 does not introduce a
runtime database repository, ORM, API service, provider, or worker.

## Reason

The execution specification fixes Pydantic v2 with unknown fields forbidden for
cross-boundary models. A declared production dependency is required so the built
package can import and validate those contracts without relying on transitive or
development-only installation. Property-based tests are required by the M1 Gate
to verify canonicalization invariants over more than fixed examples.

