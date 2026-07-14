# AGENTS.md

## Project mission

Build the Energy Equipment Operations Diagnosis Agent as a production-grade,
deployable and recoverable service.

This is a greenfield repository. Do not assume that historical implementation
paths or completion records represent existing code.

## Mandatory reading order

Before modifying code, read these files in order:

1. `docs/immutable/能源设备运维诊断Agent_详细设计.md`
2. `docs/development/CODEX_EXECUTION_SPEC.md`
3. `docs/IMPLEMENTATION_STATUS.yaml`
4. The gate definition and latest reports under `docs/gates/<module>/`
5. Any closer `AGENTS.md` applicable to the target directory

Do not begin implementation before identifying the current module and its gate.

## Authority order

Resolve conflicts in this order:

1. The user's latest explicit instruction
2. The immutable detailed design
3. `docs/development/CODEX_EXECUTION_SPEC.md`
4. Accepted ADRs
5. Module documentation
6. Tests and code comments

Lower-priority documents must not weaken higher-priority requirements.

## Immutable design

Never edit:

`docs/immutable/能源设备运维诊断Agent_详细设计.md`

Before and after every module, run:

`make verify-design`

Any checksum mismatch is a blocking failure.

Do not replace, reformat, rename, normalize line endings, or regenerate the
immutable design file.

## Module execution rule

Only implement the module marked as `current_module` in
`docs/IMPLEMENTATION_STATUS.yaml`.

Do not start a dependent module until the current module:

1. passes its unit and contract tests;
2. passes its real-service integration gate;
3. has a committed gate report;
4. has an independent review with no unresolved P0/P1/P2 issue;
5. is marked `ACCEPTED`.

A blocked live gate must be reported as `BLOCKED`. Never bypass it with a mock,
skip, fixture adapter, in-memory implementation, or health-check-only evidence.

Independent modules in the same approved wave may run concurrently only when
their file ownership is disjoint.

## Main-agent ownership

Only the main agent may modify shared files, including:

- `AGENTS.md`
- `docs/IMPLEMENTATION_STATUS.yaml`
- shared contracts
- shared configuration
- migrations
- application assembly
- `compose.yaml`
- `Makefile`
- `pyproject.toml`
- `.github/**`
- shared fixtures
- cross-domain integration and live tests

Subagents must work in isolated worktrees and only modify explicitly assigned
paths. Subagents must not commit, push, rebase, revert, or modify another
agent's files unless the main agent explicitly assigns that action.

When a shared contract is insufficient, report the required change to the main
agent instead of editing it.

## Non-negotiable engineering constraints

- No runtime Mock Provider in `full`, `staging`, `production`, or `RUN_LIVE_*`.
- Runtime services must not read fixture, generator output, or Gold files.
- Unit and contract tests may use hermetic test doubles.
- Durable requests must use Redis atomic accept, durable jobs, lease and fencing.
- Do not use in-process background tasks as reliable job acceptance.
- Do not silently switch model provider after a request failure.
- High-risk actions require persisted approval.
- Requesters, including administrators, must never approve their own requests.
- Weak tickets, unreviewed cases and graph relations are not confirmed facts.
- Public SSE must use the six frozen event types from the execution spec.
- Secrets must never enter Git, logs, documentation, snapshots or image layers.
- Do not add a production dependency without recording the reason in an ADR.
- Do not weaken a test or delete a failing test to make a gate pass.

## Real-service completion rule

A module is not complete merely because:

- code compiles;
- unit tests pass;
- containers start;
- health checks pass;
- a mock or fixture test passes;
- a live test is skipped;
- a manual screenshot exists.

A real-service gate must call the service through its production protocol,
perform authenticated reads or writes, and read back the final persistent
effect from the authoritative service.

## Required verification

Use the Make targets defined by the execution specification:

- `make verify-design`
- `make lint`
- `make typecheck`
- `make test-unit`
- `make test-contract`
- `make test-integration`
- `make test-live`
- `make test-chaos`
- `make validate-data`
- `make load-data`
- `make evaluate`
- `make performance`
- `make package-check`
- `make gate-m0` through `make gate-m11`

M0 is responsible for creating missing targets. Once created, do not bypass
them with undocumented command variants.

## Gate evidence

For every module, write a gate report under:

`docs/gates/<module>/<acceptance_run_id>.md`

The report must contain:

- commit SHA;
- environment and service versions;
- commands actually executed;
- passed, failed and skipped test counts;
- real services contacted;
- persistent readback evidence;
- performance or fault-injection results where applicable;
- unresolved blockers;
- independent reviewer result.

Never claim that an unexecuted command passed.

## Change discipline

Before coding:

1. inspect Git status;
2. identify the current module;
3. identify owned files;
4. audit the complete affected domain;
5. state the frozen implementation approach and gate.

After coding:

1. review the full diff;
2. run the required gate;
3. record evidence;
4. run an independent review;
5. update implementation status only after acceptance.

Prefer one coherent domain fix over a series of test-driven local patches.

## Documentation

When behavior, contracts, deployment, migrations or operational procedures
change, update the corresponding execution documentation, ADR, API document or
runbook.

Never modify the immutable detailed design.