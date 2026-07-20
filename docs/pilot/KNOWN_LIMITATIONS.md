# Known limitations

The Pilot build is a single modular-monolith instance with one index worker. It has no
multi-replica coordination, durable diagnosis accept, lease, fencing, worker crash
recovery, SSE replay, Last-Event-ID, Keycloak/OIDC, automatic production work-order
write, or automatic equipment operation. Circuit breaker state is process-local.
RabbitMQ performs indexing only; Neo4j is not a fact authority. Capacity work is a
small controlled stability check, not production certification. Dataset 1.3.0 still
requires project-owner business acceptance: Calibration, Regression, and the one-time
Holdout technical gates passed, but business accuracy thresholds remain unconfigured
and Holdout Top-1/Top-3 are 0.10/0.44. The graph-disabled profile preserved every main
diagnosis path but failed the unadjusted aggregate tool-success Gate because 100
expected graph `DEGRADED` attempts remain in its denominator. Real-site manuals are
not yet accepted. The checksum-protected dataset report
`reports/case_lifecycle_file_validation.json` incorrectly reports 400 orphan run and
session references; direct source and MySQL readback both verify 400 of 400 links and
zero orphans. The original report is retained unchanged and the correction is recorded
in the external readback artifact.
