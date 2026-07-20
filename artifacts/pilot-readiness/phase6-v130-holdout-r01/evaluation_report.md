# Pilot evaluation report

- Evaluation run: `phase6-v130-holdout-r01`
- Dataset: `{'id': 'pilot_medium_v1', 'version': '1.3.0', 'manifest_sha256': '5ee8c6c7042ee2c1759b0a3e8eddb2a877315bda024b14a28364254879ea2b2d', 'split': 'holdout'}`
- Waiver: `none`
- Technical gate: `PASSED`
- Business thresholds: `NOT_CONFIGURED`
- Recommendation: `CONDITIONAL_GO`

## Technical gates

| Check | Passed |
| --- | --- |
| tool_success_rate | yes |
| full_diagnosis_p95_seconds | yes |
| answerable_session_failure_rate | yes |
| invalid_evidence_reference_count | yes |
| unsupported_strong_claim_count | yes |
| gold_leak_count | yes |
| high_risk_confirmation_coverage | yes |
| prompt_injection_escape_count | yes |

## Key metrics

| Metric | Value |
| --- | ---: |
| sample_count | 50 |
| top1 | 0.1 |
| top3 | 0.44 |
| tool_success_rate | 0.96 |
| full_diagnosis_p95_seconds | 32.04534025024623 |
| first_event_p95_seconds | 0.2127992920577526 |
| session_failure_rate | 0.0 |
| invalid_evidence_reference_count | 0 |
| unsupported_strong_claim_count | 0 |
| gold_leak_count | 0 |

## Known limitations

