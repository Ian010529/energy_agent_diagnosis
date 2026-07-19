# pilot_medium_v1 1.2.0 independent offline review

## Decision

- Offline data generation and file-level validation: **PASSED**
- External service loading and index readback: **NOT EXECUTED**
- Phase 6 eligibility: **NOT YET** - load and verify in the repository Docker environment first.

## Counts

- Source documents: 24
- Parseable documents: 22
- OCR_REQUIRED documents: 2
- Reconstructed chunks: 4266
- Evaluation samples: 250

## Manual realism

- Exact duplicate rate: 18.24%
- Overall normalized exact duplicate rate (includes structured boilerplate and overlap fragments): 19.88%
- Substantive body normalized exact duplicate rate: 0.42%
- Character n-gram nearest-neighbor > 0.95: 28.69%
- Minimum per-document non-boilerplate unique sentence ratio: 53.99%
- Maximum non-boilerplate sentence repetition within one document: 18
- Section types: 正文=3160, 维护步骤=658, 告警定义=302, 注意事项=104, 表格=42

Common safety statements and model-family definitions are intentionally allowed to repeat. The validation blocks the former failure mode where a tiny sentence pool was shuffled across all documents.

## Offline gate results

- manual_validation: PASSED
- manual_mapping: PASSED
- evaluation_diversity: PASSED
- evidence_profiles: PASSED
- gold_source_mapping: PASSED
- case_lifecycle_files: PASSED
- gold_isolation: PASSED

## Required external step

Run the repository data loaders and the Phase 5 index worker, then generate RabbitMQ, Milvus and Neo4j readback reports. No external success is claimed in this package.
