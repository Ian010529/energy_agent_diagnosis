# Pilot evaluation report

- Evaluation run: `phase6-v130-regression-graph-disabled-r01`
- Dataset: `{'id': 'pilot_medium_v1', 'version': '1.3.0', 'manifest_sha256': '5ee8c6c7042ee2c1759b0a3e8eddb2a877315bda024b14a28364254879ea2b2d', 'split': 'regression'}`
- Waiver: `none`
- Technical gate: `FAILED`
- Business thresholds: `NOT_CONFIGURED`
- Recommendation: `NO_GO`

## Technical gates

| Check | Passed |
| --- | --- |
| tool_success_rate | no |
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
| sample_count | 100 |
| top1 | 0.11 |
| top3 | 0.53 |
| tool_success_rate | 0.7916666666666666 |
| full_diagnosis_p95_seconds | 27.496094374917448 |
| first_event_p95_seconds | 0.28958433400839567 |
| session_failure_rate | 0.0 |
| invalid_evidence_reference_count | 0 |
| unsupported_strong_claim_count | 0 |
| gold_leak_count | 0 |

## Known limitations

