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

## Cross-module regression prevention

### Frozen implementation boundary

Before modifying a module, freeze a concise implementation approach that covers:

1. module scope and explicit non-goals;
2. authoritative invariants;
3. service and resource ownership and isolation;
4. failure, cancellation and cleanup paths;
5. the test and evidence mapped to each Gate requirement;
6. the conditions that require rerunning the real-service Gate.

Do not begin with isolated test-driven patches. Audit the complete affected
lifecycle first and prefer one coherent root-cause fix.

### Necessity filter

Classify every proposed change or review finding as:

- `REQUIRED`: prevents a false-positive Gate, security exposure, data loss,
  incorrect persistent state, broken recovery or violation of an explicit
  higher-authority requirement;
- `DEFERRED`: optional hardening, style preference, speculative extensibility,
  refactoring or an improvement not required by the current module.

Only `REQUIRED` changes may be added while closing the current module. A review
severity label alone does not make a change required. Before modifying code,
state the concrete failure mode and why the fix belongs to the current module.

### Semantic verification

Tests must validate behavior and authoritative effects, not only source text.

- Source-string assertions may enforce a static contract but cannot be the sole
  evidence for runtime behavior.
- Profile isolation must be verified using actual project and resource identity.
- Persistence must be verified by authoritative post-restart readback.
- Authentication configuration must be verified before a probe may create,
  repair or update that configuration.
- A Gate probe must never repair the condition it is intended to validate.
- Negative-path tests must cover false-positive and self-healing probe risks.

### Source-exact Gate

A real-service Gate may run only when:

1. the worktree is clean;
2. the tested commit SHA is recorded before execution;
3. every profile uses a run-specific project and fresh resources;
4. every executed command and test count is recorded truthfully;
5. failures and skips cannot be converted into success evidence.

Any implementation or Gate-behavior change after a successful run invalidates
that run and requires a new real-service Gate. Documentation-only changes to a
Gate report or implementation status do not invalidate an otherwise
source-exact run.

### Gate rerun policy

Rerun the complete real-service Gate only when a change affects:

- runtime behavior;
- service configuration or image;
- authentication or secret handling;
- persistence, restart, recovery or cleanup;
- Gate probes, pass/fail logic or authoritative evidence.

For report wording, status metadata, comments or other non-behavioral changes,
run only the relevant static and contract checks. Do not rerun a live Gate
without a concrete affected failure mode.

### Cleanup and cancellation

Every live Gate must:

- use a unique acceptance run ID;
- use isolated project names, networks and volumes;
- register resources before starting them;
- clean resources in `finally`;
- handle normal failure, `SIGINT` and `SIGTERM`;
- verify that run-scoped containers, volumes and networks are absent afterward.

CI cancellation must not leave fixed-port services running.

### Independent review boundary

Independent review must run in an enforced read-only sandbox. The reviewer must
not modify repository files, run Docker or real services, execute the live Gate,
create acceptance evidence or change Git state.

The reviewer reports only actionable P0/P1/P2 findings. Suggestions, style
preferences and speculative hardening are non-blocking and must not trigger
implementation changes while closing the current Gate.

### Review finding closure

For every blocking review finding, record:

1. the concrete failure mode;
2. why the fix is required for the current module;
3. the affected files and lifecycle;
4. the targeted verification;
5. whether the existing Gate evidence was invalidated.

Do not fix findings one by one without first checking whether they share a
common root cause.

### Acceptance freeze

After a successful source-exact Gate and clean independent review:

1. do not change implementation code;
2. write the committed Gate report;
3. update implementation status;
4. run final immutable-design and targeted documentation checks;
5. commit and stop at the current module boundary.

Do not add optional improvements during acceptance finalization.

## Documentation

When behavior, contracts, deployment, migrations or operational procedures
change, update the corresponding execution documentation, ADR, API document or
runbook.

Never modify the immutable detailed design.
