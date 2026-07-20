# Readiness checklist

- Immutable design and Phase 5 regression verified.
- Migration `0006_phase6` upgrades a copy of the loaded database without data loss.
- Calibration and regression reports exist; Holdout is run once for the final gate.
- Technical gates pass with zero Gold leak, unsupported strong claim, unsafe high-risk
  action, invalid citation, and prompt-injection escape.
- Pilot trusted-header auth, user allowlist, Redis fail-closed writes, CORS, request
  limits, metrics auth, and secret scan pass.
- All degradation drills and dependency recovery checks pass.
- Dashboards, alerts, LangFuse, rollback, and incident procedures are verified.
- Real-site manuals remain unapproved; recommendation cannot exceed `CONDITIONAL_GO`.
