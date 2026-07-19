# pilot_medium_v1 1.2.0

Medium-scale synthetic energy-diagnosis data asset.

## Contents

- 3 sites, 400 devices, 10,000 alarms
- 3,000 maintenance tickets
- 400 reviewed-case lifecycle records
- 24 source manuals: 12 PDF, 6 DOCX, 4 Markdown, 2 TXT
- 2 image-only scanned PDFs expected to return OCR_REQUIRED
- 4266 chunks when rebuilt with the repository parser/chunker
- 920,160 Influx line-protocol points
- 250 evaluation samples with calibration/regression/holdout splits

## Important status

Repository-side independent validation and external readback have been executed.

- MySQL, MinIO, InfluxDB and the five Neo4j templates loaded successfully.
- The RabbitMQ publish/consume/ack path and Milvus/Neo4j readback passed.
- The final decision is **BLOCKED** because the real BGE-M3 duplicate rate is above the
  accepted limit.
- Holdout isolation was repaired by replacing 24 verified tickets with equivalent
  non-Holdout tickets. The final real retrieval check passes 10/10 checks.
- Phase 6 remains ineligible. See
  `reports/independent_repository_review.md` and `reports/loaded_verification.json`.

The repository retains this validated data asset and its reports. Data-generation code
is intentionally not retained.
