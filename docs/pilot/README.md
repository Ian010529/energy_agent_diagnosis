# Pilot operations pack

This pack governs the single-instance Phase 6 pre-pilot deployment. Start with
`READINESS_CHECKLIST.md`, deploy with `DEPLOYMENT_RUNBOOK.md`, and use
`INCIDENT_RUNBOOK.md` plus `DEGRADATION_MATRIX.md` during incidents.

Dataset 1.3.0 has passed external storage, real BGE-M3, Calibration, and Regression
technical gates, and its one-time Holdout technical Gate passed. The current readiness
recommendation is `CONDITIONAL_GO` because business accuracy thresholds are not
configured and Holdout Top-1/Top-3 are 0.10/0.44. The graph-disabled sensitivity
profile preserved the main diagnosis path but failed the unadjusted tool-success Gate.
Real-site manuals require a new sample review before Phase 7.
