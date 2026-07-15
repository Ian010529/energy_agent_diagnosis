CREATE TABLE schema_manifest (
  schema_name VARCHAR(64) NOT NULL,
  manifest_version INT UNSIGNED NOT NULL,
  canonicalization_version SMALLINT UNSIGNED NOT NULL,
  migration_set_digest CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  manifest_digest CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  descriptor_json JSON NOT NULL,
  created_at DATETIME(6) NOT NULL,
  CONSTRAINT pk_schema_manifest PRIMARY KEY (schema_name),
  CONSTRAINT ck_schema_manifest_canonical CHECK (canonicalization_version = 2)
) ENGINE=InnoDB DEFAULT CHARACTER SET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE auth_scope_binding (
  binding_id CHAR(36) NOT NULL,
  oidc_subject VARCHAR(255) NOT NULL,
  tenant_id VARCHAR(64) NOT NULL,
  role_name VARCHAR(32) NOT NULL,
  site_id VARCHAR(128) NULL,
  device_id VARCHAR(128) NULL,
  revoked_at DATETIME(6) NULL,
  created_at DATETIME(6) NOT NULL,
  updated_at DATETIME(6) NOT NULL,
  CONSTRAINT pk_auth_scope_binding PRIMARY KEY (binding_id),
  CONSTRAINT uq_auth_scope_binding_scope UNIQUE (oidc_subject, tenant_id, role_name, site_id, device_id),
  CONSTRAINT ck_auth_scope_binding_role CHECK (role_name IN ('viewer','operator','reviewer','admin')),
  INDEX ix_auth_scope_binding_subject_tenant (oidc_subject, tenant_id),
  INDEX ix_auth_scope_binding_resource (tenant_id, site_id, device_id)
) ENGINE=InnoDB DEFAULT CHARACTER SET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE diagnosis_session_history (
  session_id CHAR(36) NOT NULL,
  tenant_id VARCHAR(64) NOT NULL,
  owner_id VARCHAR(255) NOT NULL,
  site_id VARCHAR(128) NULL,
  device_id VARCHAR(128) NULL,
  revision BIGINT UNSIGNED NOT NULL,
  active_run_id CHAR(36) NULL,
  run_status VARCHAR(32) NULL,
  phase VARCHAR(32) NOT NULL,
  first_retained_sequence BIGINT UNSIGNED NOT NULL,
  event_high_watermark BIGINT UNSIGNED NOT NULL,
  created_at DATETIME(6) NOT NULL,
  updated_at DATETIME(6) NOT NULL,
  CONSTRAINT pk_diagnosis_session_history PRIMARY KEY (session_id),
  CONSTRAINT ck_diagnosis_session_revision CHECK (revision >= 0),
  CONSTRAINT ck_diagnosis_session_sequence CHECK (event_high_watermark >= first_retained_sequence),
  INDEX ix_diagnosis_session_owner (tenant_id, owner_id, updated_at),
  INDEX ix_diagnosis_session_resource (tenant_id, site_id, device_id)
) ENGINE=InnoDB DEFAULT CHARACTER SET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE diagnosis_acceptance_receipt (
  receipt_id CHAR(36) NOT NULL,
  tenant_id VARCHAR(64) NOT NULL,
  scope_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  idempotency_key_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  request_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  canonicalization_version SMALLINT UNSIGNED NOT NULL,
  response_json JSON NOT NULL,
  response_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  created_at DATETIME(6) NOT NULL,
  CONSTRAINT pk_diagnosis_acceptance_receipt PRIMARY KEY (receipt_id),
  CONSTRAINT uq_diagnosis_acceptance_scope UNIQUE (scope_hash, idempotency_key_hash),
  CONSTRAINT ck_diagnosis_acceptance_canonical CHECK (canonicalization_version = 2)
) ENGINE=InnoDB DEFAULT CHARACTER SET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE diagnosis_revision (
  session_id CHAR(36) NOT NULL,
  revision BIGINT UNSIGNED NOT NULL,
  payload_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  canonicalization_version SMALLINT UNSIGNED NOT NULL,
  payload_json JSON NOT NULL,
  created_at DATETIME(6) NOT NULL,
  CONSTRAINT pk_diagnosis_revision PRIMARY KEY (session_id, revision),
  CONSTRAINT fk_diagnosis_revision_session FOREIGN KEY (session_id) REFERENCES diagnosis_session_history (session_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
  CONSTRAINT ck_diagnosis_revision_positive CHECK (revision >= 1),
  CONSTRAINT ck_diagnosis_revision_canonical CHECK (canonicalization_version = 2)
) ENGINE=InnoDB DEFAULT CHARACTER SET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE diagnosis_run_history (
  run_id CHAR(36) NOT NULL,
  session_id CHAR(36) NOT NULL,
  tenant_id VARCHAR(64) NOT NULL,
  trace_id CHAR(36) NOT NULL,
  acceptance_run_id CHAR(36) NOT NULL,
  status VARCHAR(32) NOT NULL,
  phase VARCHAR(32) NOT NULL,
  slo_class VARCHAR(32) NOT NULL,
  fencing_token BIGINT UNSIGNED NOT NULL,
  attempt_count INT UNSIGNED NOT NULL,
  accepted_at DATETIME(6) NOT NULL,
  started_at DATETIME(6) NULL,
  finished_at DATETIME(6) NULL,
  error_code VARCHAR(128) NULL,
  error_json JSON NULL,
  CONSTRAINT pk_diagnosis_run_history PRIMARY KEY (run_id),
  CONSTRAINT fk_diagnosis_run_session FOREIGN KEY (session_id) REFERENCES diagnosis_session_history (session_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
  CONSTRAINT uq_diagnosis_run_acceptance UNIQUE (acceptance_run_id),
  CONSTRAINT ck_diagnosis_run_attempt CHECK (attempt_count >= 0),
  INDEX ix_diagnosis_run_session_time (session_id, accepted_at),
  INDEX ix_diagnosis_run_tenant_status (tenant_id, status, accepted_at)
) ENGINE=InnoDB DEFAULT CHARACTER SET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE diagnosis_event_history (
  event_id CHAR(36) NOT NULL,
  session_id CHAR(36) NOT NULL,
  run_id CHAR(36) NOT NULL,
  sequence BIGINT UNSIGNED NOT NULL,
  event_type VARCHAR(64) NOT NULL,
  event_version INT UNSIGNED NOT NULL,
  phase VARCHAR(32) NOT NULL,
  payload_json JSON NOT NULL,
  occurred_at DATETIME(6) NOT NULL,
  CONSTRAINT pk_diagnosis_event_history PRIMARY KEY (event_id),
  CONSTRAINT fk_diagnosis_event_session FOREIGN KEY (session_id) REFERENCES diagnosis_session_history (session_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
  CONSTRAINT fk_diagnosis_event_run FOREIGN KEY (run_id) REFERENCES diagnosis_run_history (run_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
  CONSTRAINT uq_diagnosis_event_sequence UNIQUE (session_id, sequence),
  CONSTRAINT ck_diagnosis_event_sequence CHECK (sequence >= 1),
  INDEX ix_diagnosis_event_run (run_id, sequence)
) ENGINE=InnoDB DEFAULT CHARACTER SET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE diagnosis_tool_audit (
  audit_id CHAR(36) NOT NULL,
  tenant_id VARCHAR(64) NOT NULL,
  session_id CHAR(36) NOT NULL,
  run_id CHAR(36) NOT NULL,
  trace_id CHAR(36) NOT NULL,
  tool_name VARCHAR(128) NOT NULL,
  tool_status VARCHAR(32) NOT NULL,
  parameter_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  canonicalization_version SMALLINT UNSIGNED NOT NULL,
  source_system VARCHAR(128) NOT NULL,
  latency_ms INT UNSIGNED NOT NULL,
  occurred_at DATETIME(6) NOT NULL,
  CONSTRAINT pk_diagnosis_tool_audit PRIMARY KEY (audit_id),
  CONSTRAINT fk_diagnosis_tool_audit_session FOREIGN KEY (session_id) REFERENCES diagnosis_session_history (session_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
  CONSTRAINT fk_diagnosis_tool_audit_run FOREIGN KEY (run_id) REFERENCES diagnosis_run_history (run_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
  CONSTRAINT ck_diagnosis_tool_audit_canonical CHECK (canonicalization_version = 2),
  INDEX ix_diagnosis_tool_audit_run (run_id, occurred_at),
  INDEX ix_diagnosis_tool_audit_tenant_tool (tenant_id, tool_name, occurred_at)
) ENGINE=InnoDB DEFAULT CHARACTER SET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE diagnosis_approval (
  approval_id CHAR(36) NOT NULL,
  tenant_id VARCHAR(64) NOT NULL,
  target_type VARCHAR(64) NOT NULL,
  target_id VARCHAR(255) NOT NULL,
  action_name VARCHAR(128) NOT NULL,
  requester_id VARCHAR(255) NOT NULL,
  state VARCHAR(16) NOT NULL,
  revision BIGINT UNSIGNED NOT NULL,
  request_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  idempotency_scope_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  idempotency_key_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  decision_actor_id VARCHAR(255) NULL,
  decision_actor_role VARCHAR(32) NULL,
  decision_reason TEXT NULL,
  emergency BOOLEAN NOT NULL,
  created_at DATETIME(6) NOT NULL,
  decided_at DATETIME(6) NULL,
  CONSTRAINT pk_diagnosis_approval PRIMARY KEY (approval_id),
  CONSTRAINT uq_diagnosis_approval_idempotency UNIQUE (idempotency_scope_hash, idempotency_key_hash),
  CONSTRAINT ck_diagnosis_approval_state CHECK (state IN ('PENDING','APPROVED','REJECTED','CANCELLED')),
  CONSTRAINT ck_diagnosis_approval_no_self_review CHECK (decision_actor_id IS NULL OR decision_actor_id <> requester_id),
  CONSTRAINT ck_diagnosis_approval_emergency_reason CHECK (emergency = FALSE OR decision_reason IS NOT NULL),
  INDEX ix_diagnosis_approval_target (tenant_id, target_type, target_id),
  INDEX ix_diagnosis_approval_state (tenant_id, state, created_at)
) ENGINE=InnoDB DEFAULT CHARACTER SET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE diagnosis_approval_audit (
  audit_id CHAR(36) NOT NULL,
  approval_id CHAR(36) NOT NULL,
  revision BIGINT UNSIGNED NOT NULL,
  actor_id VARCHAR(255) NOT NULL,
  action_name VARCHAR(64) NOT NULL,
  state VARCHAR(16) NOT NULL,
  reason TEXT NULL,
  trace_id CHAR(36) NOT NULL,
  occurred_at DATETIME(6) NOT NULL,
  CONSTRAINT pk_diagnosis_approval_audit PRIMARY KEY (audit_id),
  CONSTRAINT fk_diagnosis_approval_audit_approval FOREIGN KEY (approval_id) REFERENCES diagnosis_approval (approval_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
  CONSTRAINT uq_diagnosis_approval_audit_revision UNIQUE (approval_id, revision),
  INDEX ix_diagnosis_approval_audit_time (approval_id, occurred_at)
) ENGINE=InnoDB DEFAULT CHARACTER SET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE diagnosis_approval_outbox (
  event_id CHAR(36) NOT NULL,
  approval_id CHAR(36) NOT NULL,
  event_type VARCHAR(128) NOT NULL,
  event_version INT UNSIGNED NOT NULL,
  idempotency_key_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  payload_json JSON NOT NULL,
  publish_state VARCHAR(24) NOT NULL,
  attempt_count INT UNSIGNED NOT NULL,
  available_at DATETIME(6) NOT NULL,
  published_at DATETIME(6) NULL,
  created_at DATETIME(6) NOT NULL,
  CONSTRAINT pk_diagnosis_approval_outbox PRIMARY KEY (event_id),
  CONSTRAINT fk_diagnosis_approval_outbox_approval FOREIGN KEY (approval_id) REFERENCES diagnosis_approval (approval_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
  CONSTRAINT uq_diagnosis_approval_outbox_idempotency UNIQUE (idempotency_key_hash),
  INDEX ix_diagnosis_approval_outbox_pending (publish_state, available_at)
) ENGINE=InnoDB DEFAULT CHARACTER SET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE diagnosis_confirmation_token (
  token_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  approval_id CHAR(36) NOT NULL,
  target_type VARCHAR(64) NOT NULL,
  target_id VARCHAR(255) NOT NULL,
  action_name VARCHAR(128) NOT NULL,
  actor_id VARCHAR(255) NOT NULL,
  nonce CHAR(36) NOT NULL,
  expires_at DATETIME(6) NOT NULL,
  consumed_at DATETIME(6) NULL,
  created_at DATETIME(6) NOT NULL,
  CONSTRAINT pk_diagnosis_confirmation_token PRIMARY KEY (token_hash),
  CONSTRAINT fk_diagnosis_confirmation_approval FOREIGN KEY (approval_id) REFERENCES diagnosis_approval (approval_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
  CONSTRAINT uq_diagnosis_confirmation_nonce UNIQUE (nonce),
  INDEX ix_diagnosis_confirmation_target (target_type, target_id, action_name)
) ENGINE=InnoDB DEFAULT CHARACTER SET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE diagnosis_case (
  case_id CHAR(36) NOT NULL,
  tenant_id VARCHAR(64) NOT NULL,
  source_session_id CHAR(36) NOT NULL,
  source_ticket_id VARCHAR(255) NULL,
  submitter_id VARCHAR(255) NOT NULL,
  device_type VARCHAR(128) NOT NULL,
  device_model VARCHAR(128) NOT NULL,
  alarm_name VARCHAR(255) NOT NULL,
  symptom_summary TEXT NOT NULL,
  timeseries_features JSON NOT NULL,
  root_cause TEXT NULL,
  resolution_steps JSON NOT NULL,
  safety_notes JSON NOT NULL,
  evidence_refs JSON NOT NULL,
  status VARCHAR(24) NOT NULL,
  index_state VARCHAR(24) NOT NULL,
  case_version BIGINT UNSIGNED NOT NULL,
  content_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  canonicalization_version SMALLINT UNSIGNED NOT NULL,
  supersedes_case_id CHAR(36) NULL,
  created_at DATETIME(6) NOT NULL,
  updated_at DATETIME(6) NOT NULL,
  CONSTRAINT pk_diagnosis_case PRIMARY KEY (case_id),
  CONSTRAINT fk_diagnosis_case_session FOREIGN KEY (source_session_id) REFERENCES diagnosis_session_history (session_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
  CONSTRAINT fk_diagnosis_case_supersedes FOREIGN KEY (supersedes_case_id) REFERENCES diagnosis_case (case_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
  CONSTRAINT uq_diagnosis_case_version UNIQUE (case_id, case_version),
  CONSTRAINT ck_diagnosis_case_status CHECK (status IN ('DRAFT','PENDING_REVIEW','APPROVED','REJECTED','DISABLED','SUPERSEDED')),
  CONSTRAINT ck_diagnosis_case_index_state CHECK (index_state IN ('PENDING','QUEUED','INDEXED','DEGRADED','FAILED','TOMBSTONED')),
  CONSTRAINT ck_diagnosis_case_canonical CHECK (canonicalization_version = 2),
  INDEX ix_diagnosis_case_search (tenant_id, device_type, device_model, alarm_name),
  INDEX ix_diagnosis_case_status (tenant_id, status, index_state)
) ENGINE=InnoDB DEFAULT CHARACTER SET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE diagnosis_case_review (
  review_id CHAR(36) NOT NULL,
  case_id CHAR(36) NOT NULL,
  case_version BIGINT UNSIGNED NOT NULL,
  reviewer_id VARCHAR(255) NOT NULL,
  review_result VARCHAR(32) NOT NULL,
  review_reason TEXT NOT NULL,
  root_cause TEXT NULL,
  evidence_refs JSON NOT NULL,
  trace_id CHAR(36) NOT NULL,
  reviewed_at DATETIME(6) NOT NULL,
  CONSTRAINT pk_diagnosis_case_review PRIMARY KEY (review_id),
  CONSTRAINT fk_diagnosis_case_review_case FOREIGN KEY (case_id) REFERENCES diagnosis_case (case_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
  CONSTRAINT uq_diagnosis_case_review_version UNIQUE (case_id, case_version),
  CONSTRAINT ck_diagnosis_case_review_result CHECK (review_result IN ('APPROVED','REJECTED','NEEDS_MORE_INFO')),
  INDEX ix_diagnosis_case_review_reviewer (reviewer_id, reviewed_at)
) ENGINE=InnoDB DEFAULT CHARACTER SET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE diagnosis_case_outbox (
  event_id CHAR(36) NOT NULL,
  case_id CHAR(36) NOT NULL,
  case_version BIGINT UNSIGNED NOT NULL,
  event_type VARCHAR(128) NOT NULL,
  event_version INT UNSIGNED NOT NULL,
  idempotency_key_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  payload_json JSON NOT NULL,
  publish_state VARCHAR(24) NOT NULL,
  attempt_count INT UNSIGNED NOT NULL,
  available_at DATETIME(6) NOT NULL,
  published_at DATETIME(6) NULL,
  created_at DATETIME(6) NOT NULL,
  CONSTRAINT pk_diagnosis_case_outbox PRIMARY KEY (event_id),
  CONSTRAINT fk_diagnosis_case_outbox_case FOREIGN KEY (case_id) REFERENCES diagnosis_case (case_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
  CONSTRAINT uq_diagnosis_case_outbox_idempotency UNIQUE (idempotency_key_hash),
  INDEX ix_diagnosis_case_outbox_pending (publish_state, available_at)
) ENGINE=InnoDB DEFAULT CHARACTER SET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE diagnosis_model_call_attempt (
  call_id CHAR(36) NOT NULL,
  attempt_no INT UNSIGNED NOT NULL,
  tenant_id VARCHAR(64) NOT NULL,
  session_id CHAR(36) NOT NULL,
  run_id CHAR(36) NOT NULL,
  trace_id CHAR(36) NOT NULL,
  provider VARCHAR(64) NOT NULL,
  model_name VARCHAR(128) NOT NULL,
  endpoint_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  request_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  prompt_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  canonicalization_version SMALLINT UNSIGNED NOT NULL,
  status VARCHAR(24) NOT NULL,
  prompt_tokens BIGINT UNSIGNED NULL,
  completion_tokens BIGINT UNSIGNED NULL,
  total_tokens BIGINT UNSIGNED NULL,
  estimated_cost DECIMAL(20,8) NULL,
  error_code VARCHAR(128) NULL,
  started_at DATETIME(6) NOT NULL,
  finished_at DATETIME(6) NULL,
  CONSTRAINT pk_diagnosis_model_attempt PRIMARY KEY (call_id, attempt_no),
  CONSTRAINT fk_diagnosis_model_attempt_session FOREIGN KEY (session_id) REFERENCES diagnosis_session_history (session_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
  CONSTRAINT fk_diagnosis_model_attempt_run FOREIGN KEY (run_id) REFERENCES diagnosis_run_history (run_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
  CONSTRAINT ck_diagnosis_model_attempt_canonical CHECK (canonicalization_version = 2),
  INDEX ix_diagnosis_model_attempt_run (run_id, started_at)
) ENGINE=InnoDB DEFAULT CHARACTER SET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE diagnosis_model_settlement (
  settlement_id CHAR(36) NOT NULL,
  call_id CHAR(36) NOT NULL,
  tenant_id VARCHAR(64) NOT NULL,
  provider VARCHAR(64) NOT NULL,
  model_name VARCHAR(128) NOT NULL,
  state VARCHAR(32) NOT NULL,
  reserved_tokens BIGINT UNSIGNED NOT NULL,
  actual_tokens BIGINT UNSIGNED NULL,
  actual_cost DECIMAL(20,8) NULL,
  attempt_count INT UNSIGNED NOT NULL,
  created_at DATETIME(6) NOT NULL,
  settled_at DATETIME(6) NULL,
  CONSTRAINT pk_diagnosis_model_settlement PRIMARY KEY (settlement_id),
  CONSTRAINT uq_diagnosis_model_settlement_call UNIQUE (call_id),
  CONSTRAINT ck_diagnosis_model_settlement_state CHECK (state IN ('PENDING','SETTLED','FAILED','MANUAL_REDRIVE_REQUIRED')),
  INDEX ix_diagnosis_model_settlement_pending (state, created_at)
) ENGINE=InnoDB DEFAULT CHARACTER SET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE diagnosis_index_release_pointer (
  tenant_id VARCHAR(64) NOT NULL,
  index_group VARCHAR(64) NOT NULL,
  revision BIGINT UNSIGNED NOT NULL,
  release_id CHAR(36) NOT NULL,
  fencing_token BIGINT UNSIGNED NOT NULL,
  opensearch_target VARCHAR(255) NOT NULL,
  milvus_target VARCHAR(255) NOT NULL,
  generation_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  activated_by VARCHAR(255) NOT NULL,
  activated_at DATETIME(6) NOT NULL,
  CONSTRAINT pk_diagnosis_index_pointer PRIMARY KEY (tenant_id, index_group),
  CONSTRAINT uq_diagnosis_index_target UNIQUE (tenant_id, release_id, fencing_token),
  CONSTRAINT ck_diagnosis_index_revision CHECK (revision >= 1)
) ENGINE=InnoDB DEFAULT CHARACTER SET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE expert_template (
  template_id CHAR(36) NOT NULL,
  tenant_id VARCHAR(64) NOT NULL,
  scenario_key VARCHAR(128) NOT NULL,
  template_version BIGINT UNSIGNED NOT NULL,
  content_json JSON NOT NULL,
  content_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  canonicalization_version SMALLINT UNSIGNED NOT NULL,
  status VARCHAR(24) NOT NULL,
  reviewer_id VARCHAR(255) NULL,
  review_reason TEXT NULL,
  reviewed_at DATETIME(6) NULL,
  created_at DATETIME(6) NOT NULL,
  updated_at DATETIME(6) NOT NULL,
  active_scenario_key VARCHAR(128) GENERATED ALWAYS AS (CASE WHEN status = 'ACTIVE' THEN scenario_key ELSE NULL END) STORED,
  CONSTRAINT pk_expert_template PRIMARY KEY (template_id),
  CONSTRAINT uq_expert_template_version UNIQUE (tenant_id, scenario_key, template_version),
  CONSTRAINT uq_expert_template_active UNIQUE (tenant_id, active_scenario_key),
  CONSTRAINT ck_expert_template_status CHECK (status IN ('DRAFT','PENDING_REVIEW','ACTIVE','REJECTED','SUPERSEDED')),
  CONSTRAINT ck_expert_template_canonical CHECK (canonicalization_version = 2),
  INDEX ix_expert_template_status (tenant_id, status, updated_at)
) ENGINE=InnoDB DEFAULT CHARACTER SET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE manual_review_record (
  review_id CHAR(36) NOT NULL,
  tenant_id VARCHAR(64) NOT NULL,
  document_id VARCHAR(255) NOT NULL,
  document_version VARCHAR(128) NOT NULL,
  source_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  review_result VARCHAR(24) NOT NULL,
  reviewer_id VARCHAR(255) NOT NULL,
  review_reason TEXT NOT NULL,
  reviewed_at DATETIME(6) NOT NULL,
  CONSTRAINT pk_manual_review_record PRIMARY KEY (review_id),
  CONSTRAINT uq_manual_review_identity UNIQUE (tenant_id, document_id, document_version, source_hash),
  CONSTRAINT ck_manual_review_result CHECK (review_result IN ('APPROVED','REJECTED')),
  INDEX ix_manual_review_document (tenant_id, document_id, reviewed_at)
) ENGINE=InnoDB DEFAULT CHARACTER SET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE trace_outbox (
  trace_id CHAR(36) NOT NULL,
  tenant_id VARCHAR(64) NOT NULL,
  session_id CHAR(36) NOT NULL,
  run_id CHAR(36) NOT NULL,
  state VARCHAR(24) NOT NULL,
  payload_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  payload_json JSON NOT NULL,
  deterministic_object_id VARCHAR(255) NOT NULL,
  attempt_count INT UNSIGNED NOT NULL,
  available_at DATETIME(6) NOT NULL,
  exported_at DATETIME(6) NULL,
  verified_at DATETIME(6) NULL,
  created_at DATETIME(6) NOT NULL,
  CONSTRAINT pk_trace_outbox PRIMARY KEY (trace_id),
  CONSTRAINT fk_trace_outbox_session FOREIGN KEY (session_id) REFERENCES diagnosis_session_history (session_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
  CONSTRAINT fk_trace_outbox_run FOREIGN KEY (run_id) REFERENCES diagnosis_run_history (run_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
  CONSTRAINT uq_trace_outbox_object UNIQUE (deterministic_object_id),
  CONSTRAINT ck_trace_outbox_state CHECK (state IN ('PENDING_EXPORT','EXPORTED','VERIFIED')),
  INDEX ix_trace_outbox_pending (state, available_at)
) ENGINE=InnoDB DEFAULT CHARACTER SET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE import_ledger (
  acceptance_run_id CHAR(36) NOT NULL,
  service_name VARCHAR(128) NOT NULL,
  resource_type VARCHAR(128) NOT NULL,
  resource_id VARCHAR(255) NOT NULL,
  request_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  readback_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  canonicalization_version SMALLINT UNSIGNED NOT NULL,
  result_state VARCHAR(24) NOT NULL,
  imported_at DATETIME(6) NOT NULL,
  verified_at DATETIME(6) NULL,
  CONSTRAINT pk_import_ledger PRIMARY KEY (acceptance_run_id, service_name, resource_type, resource_id),
  CONSTRAINT ck_import_ledger_canonical CHECK (canonicalization_version = 2),
  INDEX ix_import_ledger_state (acceptance_run_id, result_state)
) ENGINE=InnoDB DEFAULT CHARACTER SET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
