# pilot_medium_v1 1.2.0 repository independent review

## Decision

- Final status: **BLOCKED**
- Phase 6 eligible: **No**
- Immutable detailed design: unchanged
- Phase 5 check: passed

## Passed checks

- Original package checksums: 62/62 matched before repository-side reports were written.
- Counts: 3 sites, 400 devices, 10,000 alarms, 3,000 tickets, 400 cases,
  24 source documents, 920,160 time-series points and 250 evaluation samples.
- Repository parser/chunker rebuild: 4,266 chunks and 2 OCR_REQUIRED documents.
- Current document mapping, evaluation diversity, Gold source mapping, natural-language
  hygiene, time-series causality and Gold isolation passed.
- Case lifecycle: 400 sessions/runs/reviews, 465 review events, 465 audit events,
  no orphan, self-review or invalid strong-evidence case.
- Independent evidence: 24 approved facts; every fact has at least 5 distinct cases,
  source tickets and diagnosis sessions. The required minimum is 2.
- RabbitMQ accounting: 2,022 jobs/outbox records, 2,022 confirmed publishes,
  2,022 consumed and acknowledged, 2,016 indexed, 6 stale, 0 retry, 0 DLQ and 0 failure.
- Milvus readback: 3,510 manual chunks, 1,800 verified tickets and 200 approved cases.
- Neo4j readback: 237 nodes and 823 relations. The 200 approved cases each contributed
  exactly 4 relations; no random relations were introduced.
- Holdout isolation: 24 verified tickets previously attached to Holdout devices were
  replaced with audited non-Holdout tickets. Counts remain 3,000 total and 1,800
  verified; no approved case depended on the removed IDs.
- All ten real retrieval sanity checks passed after replacement.

## Blocking failure

1. Real `BAAI/bge-m3` validation over all 3,510 non-controlled chunks found:
   - 777 normalized exact duplicates (22.14%);
   - 1,715 nearest neighbors above 0.95 similarity (48.86%);
   - 3,222 nearest neighbors above 0.90 similarity (91.79%).

   This exceeds both the frozen 3% gate and the later approximately 12.5% realistic
   deviation accepted by the user. Ticket composite exact duplicates remain zero.

## Non-blocking recorded deviation

The graph contains 237 nodes, below the 250-node lower target, while its 823 relations
are within the required 800-1,500 range. The user's priority—multiple independent case
sources for the same fact—is satisfied, so no artificial nodes or relations were added.

The Holdout repair mapping is recorded in `reports/holdout_ticket_replacements.json`.
Per the user's instruction, data-generation code is not retained. The manual-similarity
failure remains recorded before Phase 6 can be declared independently passed.
