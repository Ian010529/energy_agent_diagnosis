# M1 Frozen Implementation Plan

## Baseline and ownership

- Base `origin/main`: `3bc15f77229a7fa5ba5ab2b82fa2892ac22773e8`
- Branch: `codex/m1-shared-contracts-migrations`
- M0 remains `ACCEPTED`; its accepted commit and Gate report are immutable facts.
- The main agent exclusively owns all M1 writes. Audit subagents are read-only.
- The immutable design checksum is
  `c559a530387de5fc1afced506e406967e74c18ed76e659b4b062c2051b615a11`.

## Scope and explicit non-goals

M1 freezes shared enums and DTOs, HTTP error semantics, public SSE schemas, the
internal event envelope, canonicalization v2, the typed configuration boundary,
control/ops database migrations and manifests, and the Redis atomic preflight
failure contract. It also supplies unit, contract, migration integration, and
real MySQL/Redis Gate evidence.

M1 does not implement API routes, OIDC/JWT/RBAC services, approvals behavior,
Agent/LangGraph, durable workers, Tool execution, providers, retrieval/RAG,
model calls, observability exporters, data generation/loading, or a frontend.

## Authoritative contract inventory and audit conflicts

The single package `src/energy_agent/contracts/` owns `RunStatus`,
`DiagnosisPhase`, `AlarmDiagnosisStatus`, `ToolStatus`, `ApprovalState`,
`CaseStatus`, `IndexState`, HTTP error DTOs, `RunAcceptedResponse`, `ToolResult`,
`ToolMeta`, `EventEnvelope`, public SSE events, approval/case/index/model DTOs,
and schema-manifest/migration-result DTOs. Every boundary model uses Pydantic v2
with `extra="forbid"`.

The greenfield repository contains no prior implementation or duplicate Python
definition. Three mutable-spec conflicts are resolved by the user's latest
instruction:

1. Canonical JSON v1 becomes canonicalization v2, with only version 2 emitted.
2. `CaseState` becomes `CaseStatus`; no second public alias is retained.
3. `EventEnvelope` uses `idempotency_key`; hash-only persistence columns retain
   their explicit `idempotency_key_hash` security meaning.

`ErrorEnvelope.acceptance_run_id` is a required string in new M1 objects. Legacy
`null` adaptation, if needed later, belongs at a future read boundary.
`SUCCESS` is accepted only by the explicit legacy ToolResult normalizer and is
immediately mapped to `OK`.

## Canonicalization v2

`src/energy_agent/core/canonicalization.py` is the only implementation. It emits
compact UTF-8 JSON, normalizes strings and keys to NFC, sorts normalized object
keys by Unicode code point, preserves null and array order, renders decimal
numbers without exponents or negative zero, converts aware datetimes to UTC with
six microseconds and `Z`, rejects naive datetimes, non-string keys, normalized-key
collisions, unsupported values, NaN, and infinity, and computes SHA-256.

Decimal values are canonicalized by numeric value: insignificant trailing zeros
are removed, while zero is always `0`. Finite floats pass through the same exact
decimal rendering of their shortest Python JSON value. Persisted hash DTOs carry
both `canonicalization_version=2` and the lowercase digest.

Verification uses committed cross-language vectors plus Hypothesis properties for
key insertion order, NFC, decimal/negative-zero, timezone equivalence, invalid
floats, deterministic hashes, and field-change sensitivity.

## Typed configuration boundary

`src/energy_agent/core/config.py` is the sole business configuration assembly
boundary. Models cover app, auth, control MySQL, ops MySQL, Redis, storage, model
gateway, retrieval, observability, deployment profile, and secret references.
They store secret environment names/references, never secret values.

Protected `full`, `staging`, `production`, and `live` profiles reject runtime
mock/fixture/sandbox/Gold/JSON readers, `d3_dev`, placeholder secret references,
and model tuples outside the execution-spec allowlist. Static tests reject direct
`os.environ`/`os.getenv` reads elsewhere under `src/energy_agent`.

## Control and ops migration graph

Both schemas start at `0001` and use InnoDB, `utf8mb4`,
`utf8mb4_0900_ai_ci`, and UTC `DATETIME(6)`. Control `0001` contains migration
ledgers, `schema_manifest`, and all 22 control tables declared in section 9.1.
Ops `0001` contains migration ledgers, `schema_manifest`, and all 10 ops tables
declared in section 9.2. Every PK, unique key, index, check, and FK has an explicit
stable name. Append-only audit, attempt, revision, ledger, and outbox facts never
use cascading deletion.

Migration graph:

```text
empty control DB -> control/0001_initial.sql -> control manifest v1
empty ops DB     -> ops/0001_initial.sql     -> ops manifest v1
```

## Manifest, interruption, idempotency, and drift refusal

The migration runner hashes immutable migration bytes before any DDL, obtains a
database-scoped advisory lock, and records version/file checksum plus statement
progress. MySQL DDL is treated as implicitly committed: on resume, each statement
is reconciled against exact information-schema structure before its step is
recorded. Existing incompatible objects fail closed; `IF NOT EXISTS` is not used
to hide drift.

Committed descriptors cover table engine/collation, ordered columns and their
types/null/default/extra/collation, PK/unique/ordinary indexes including order and
visibility, CHECK expressions, and FKs with update/delete rules. Read-only verify
compares the actual descriptor, descriptor digest, migration-set digest, and
stored `schema_manifest`; it never migrates or repairs. Published migration byte
changes and live schema drift fail closed.

`diagnosis_revision` has PK `(session_id, revision)`, payload digest, and
canonicalization version. The Gate proves same revision/same digest is idempotent
and same revision/different digest conflicts without changing the original row.

## Redis atomic failure contract

The M1 Lua contract checks the type of every key before its first write. Any type
mismatch returns a structured failure with zero writes. The live Gate seeds a
late key with the wrong type, calls the script through authenticated Redis, and
compares complete before/after snapshots across all candidate keys.

## Files owned by M1

- `src/energy_agent/contracts/**`
- `src/energy_agent/core/{config,errors,canonicalization}.py`
- `migrations/{control,ops}/0001_initial.sql`
- `schema/descriptor/**`
- `scripts/migrations/**`, `scripts/m1_gate.py`
- M1 unit/contract/integration/live tests
- `docs/development/M1_PLAN.md`, the canonicalization conflict lines in the
  execution spec, `docs/IMPLEMENTATION_STATUS.yaml`, and `docs/gates/M1/**`
- `Makefile`, `pyproject.toml`, `uv.lock`, `.github/workflows/ci.yml`, and only
  backward-compatible Compose port isolation required by the Gate
- ADR 0002, explicitly authorized by the user

## Test and Gate matrix

| Gate requirement | Evidence |
|---|---|
| enums/DTO/error/SSE/EventEnvelope | strict Pydantic contract tests and JSON Schema |
| legacy ToolResult | `SUCCESS -> OK` read-boundary tests; new writes reject it |
| canonicalization v2 | fixed vectors, negative cases, Hypothesis properties |
| typed protected config | profile/model/secret/runtime-source positive and negative tests |
| empty control/ops install | real MySQL migration plus information-schema readback |
| interrupted migration recovery | Gate-only child-process failpoint, SIGKILL, fresh-process resume |
| idempotent rerun/checksum refusal | real migration rerun and mutated temporary migration copy |
| complete manifest/drift refusal | committed descriptor comparison and isolated drift databases |
| UTC/charset/collation | session variables and information-schema assertions |
| revision idempotency/conflict | transactional MySQL insert/readback helper |
| Redis zero-partial-write | authenticated real Redis Lua snapshot test |
| M0 regression | unchanged `make gate-m0` after M1 implementation commit |

Live/staging evidence must report zero skips. A successful run is valid only for
the clean implementation commit recorded before execution.

## Failure, cancellation, cleanup, and rollback

Each Gate uses a UUIDv7 acceptance run ID, unique Compose project, random local
credentials, unique control/ops databases, and registered resources. Signal
handlers and `finally` cleanup remove only run-scoped unpublished databases,
containers, networks, volumes, and temporary files, then prove they are absent.
No fixed published database is rolled back. Before M1 publication, rollback means
dropping only the isolated Gate databases. After acceptance, `0001` is immutable;
future changes require a new forward migration.

## Gate rerun boundary and known blockers

Any change to runtime contracts, canonicalization, configuration, migration SQL,
manifest logic, Redis Lua, Compose service behavior, or Gate pass/fail/readback
logic invalidates prior M1 live evidence and requires the full Gate again.
Documentation-only report/status wording requires only immutable-design and
targeted static/contract checks.

The dependency-recording blocker was resolved by explicit user authorization for
ADR 0002. No other blocker is known at plan freeze.
