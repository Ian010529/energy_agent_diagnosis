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

CREATE TABLE asset_device (
  tenant_id VARCHAR(64) NOT NULL,
  device_id VARCHAR(128) NOT NULL,
  source_system VARCHAR(128) NOT NULL,
  source_version VARCHAR(128) NOT NULL,
  site_id VARCHAR(128) NOT NULL,
  device_type VARCHAR(128) NOT NULL,
  device_model VARCHAR(128) NOT NULL,
  manufacturer VARCHAR(255) NOT NULL,
  commission_time DATETIME(6) NULL,
  status VARCHAR(32) NOT NULL,
  rated_power DECIMAL(20,6) NULL,
  payload_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  canonicalization_version SMALLINT UNSIGNED NOT NULL,
  created_at DATETIME(6) NOT NULL,
  updated_at DATETIME(6) NOT NULL,
  CONSTRAINT pk_asset_device PRIMARY KEY (tenant_id, device_id),
  CONSTRAINT uq_asset_device_source UNIQUE (tenant_id, source_system, device_id, source_version),
  CONSTRAINT ck_asset_device_canonical CHECK (canonicalization_version = 2),
  INDEX ix_asset_device_site (tenant_id, site_id, device_type)
) ENGINE=InnoDB DEFAULT CHARACTER SET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE asset_hierarchy (
  tenant_id VARCHAR(64) NOT NULL,
  node_id VARCHAR(128) NOT NULL,
  parent_node_id VARCHAR(128) NULL,
  node_type VARCHAR(64) NOT NULL,
  node_name VARCHAR(255) NOT NULL,
  site_id VARCHAR(128) NULL,
  revision BIGINT UNSIGNED NOT NULL,
  created_at DATETIME(6) NOT NULL,
  updated_at DATETIME(6) NOT NULL,
  CONSTRAINT pk_asset_hierarchy PRIMARY KEY (tenant_id, node_id),
  CONSTRAINT fk_asset_hierarchy_parent FOREIGN KEY (tenant_id, parent_node_id) REFERENCES asset_hierarchy (tenant_id, node_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
  CONSTRAINT ck_asset_hierarchy_revision CHECK (revision >= 1),
  INDEX ix_asset_hierarchy_parent (tenant_id, parent_node_id),
  INDEX ix_asset_hierarchy_site (tenant_id, site_id)
) ENGINE=InnoDB DEFAULT CHARACTER SET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE enterprise_id_mapping (
  tenant_id VARCHAR(64) NOT NULL,
  source_system VARCHAR(128) NOT NULL,
  external_id VARCHAR(255) NOT NULL,
  entity_type VARCHAR(64) NOT NULL,
  internal_id VARCHAR(255) NOT NULL,
  source_version VARCHAR(128) NOT NULL,
  created_at DATETIME(6) NOT NULL,
  updated_at DATETIME(6) NOT NULL,
  CONSTRAINT pk_enterprise_id_mapping PRIMARY KEY (tenant_id, source_system, entity_type, external_id),
  CONSTRAINT uq_enterprise_id_internal UNIQUE (tenant_id, source_system, entity_type, internal_id),
  INDEX ix_enterprise_id_mapping_internal (tenant_id, internal_id)
) ENGINE=InnoDB DEFAULT CHARACTER SET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE alarm_event_version (
  tenant_id VARCHAR(64) NOT NULL,
  alarm_id VARCHAR(255) NOT NULL,
  source_version VARCHAR(128) NOT NULL,
  source_system VARCHAR(128) NOT NULL,
  device_id VARCHAR(128) NOT NULL,
  site_id VARCHAR(128) NOT NULL,
  alarm_name VARCHAR(255) NOT NULL,
  alarm_level VARCHAR(32) NOT NULL,
  alarm_status VARCHAR(32) NOT NULL,
  occurred_at DATETIME(6) NOT NULL,
  payload_json JSON NOT NULL,
  payload_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  canonicalization_version SMALLINT UNSIGNED NOT NULL,
  ingested_at DATETIME(6) NOT NULL,
  CONSTRAINT pk_alarm_event_version PRIMARY KEY (tenant_id, alarm_id, source_version),
  CONSTRAINT fk_alarm_event_device FOREIGN KEY (tenant_id, device_id) REFERENCES asset_device (tenant_id, device_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
  CONSTRAINT ck_alarm_event_canonical CHECK (canonicalization_version = 2),
  INDEX ix_alarm_event_device_time (tenant_id, device_id, occurred_at),
  INDEX ix_alarm_event_site_time (tenant_id, site_id, occurred_at)
) ENGINE=InnoDB DEFAULT CHARACTER SET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE alarm_delivery (
  delivery_id CHAR(36) NOT NULL,
  tenant_id VARCHAR(64) NOT NULL,
  alarm_id VARCHAR(255) NOT NULL,
  source_version VARCHAR(128) NOT NULL,
  delivery_attempt INT UNSIGNED NOT NULL,
  redrive_generation INT UNSIGNED NOT NULL,
  business_status VARCHAR(32) NOT NULL,
  broker_message_id VARCHAR(255) NULL,
  last_error_code VARCHAR(128) NULL,
  next_attempt_at DATETIME(6) NULL,
  delivered_at DATETIME(6) NULL,
  created_at DATETIME(6) NOT NULL,
  updated_at DATETIME(6) NOT NULL,
  CONSTRAINT pk_alarm_delivery PRIMARY KEY (delivery_id),
  CONSTRAINT fk_alarm_delivery_event FOREIGN KEY (tenant_id, alarm_id, source_version) REFERENCES alarm_event_version (tenant_id, alarm_id, source_version) ON UPDATE RESTRICT ON DELETE RESTRICT,
  CONSTRAINT uq_alarm_delivery_generation UNIQUE (tenant_id, alarm_id, source_version, redrive_generation, delivery_attempt),
  INDEX ix_alarm_delivery_pending (business_status, next_attempt_at)
) ENGINE=InnoDB DEFAULT CHARACTER SET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE alarm_diagnosis_outbox (
  event_id CHAR(36) NOT NULL,
  tenant_id VARCHAR(64) NOT NULL,
  alarm_id VARCHAR(255) NOT NULL,
  source_version VARCHAR(128) NOT NULL,
  redrive_generation INT UNSIGNED NOT NULL,
  event_type VARCHAR(128) NOT NULL,
  event_version INT UNSIGNED NOT NULL,
  idempotency_key_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  payload_json JSON NOT NULL,
  publish_state VARCHAR(24) NOT NULL,
  attempt_count INT UNSIGNED NOT NULL,
  available_at DATETIME(6) NOT NULL,
  published_at DATETIME(6) NULL,
  created_at DATETIME(6) NOT NULL,
  CONSTRAINT pk_alarm_diagnosis_outbox PRIMARY KEY (event_id),
  CONSTRAINT fk_alarm_outbox_event FOREIGN KEY (tenant_id, alarm_id, source_version) REFERENCES alarm_event_version (tenant_id, alarm_id, source_version) ON UPDATE RESTRICT ON DELETE RESTRICT,
  CONSTRAINT uq_alarm_outbox_idempotency UNIQUE (idempotency_key_hash),
  INDEX ix_alarm_outbox_pending (publish_state, available_at)
) ENGINE=InnoDB DEFAULT CHARACTER SET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE telemetry_metric_catalog (
  tenant_id VARCHAR(64) NOT NULL,
  metric_name VARCHAR(128) NOT NULL,
  device_type VARCHAR(128) NOT NULL,
  measurement VARCHAR(128) NOT NULL,
  unit VARCHAR(64) NOT NULL,
  minimum_value DECIMAL(24,8) NULL,
  maximum_value DECIMAL(24,8) NULL,
  quality_codes JSON NOT NULL,
  revision BIGINT UNSIGNED NOT NULL,
  active BOOLEAN NOT NULL,
  created_at DATETIME(6) NOT NULL,
  updated_at DATETIME(6) NOT NULL,
  CONSTRAINT pk_telemetry_metric_catalog PRIMARY KEY (tenant_id, metric_name, device_type),
  CONSTRAINT ck_telemetry_metric_range CHECK (minimum_value IS NULL OR maximum_value IS NULL OR minimum_value <= maximum_value),
  CONSTRAINT ck_telemetry_metric_revision CHECK (revision >= 1),
  INDEX ix_telemetry_metric_measurement (tenant_id, measurement, active)
) ENGINE=InnoDB DEFAULT CHARACTER SET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE work_order (
  tenant_id VARCHAR(64) NOT NULL,
  ticket_id VARCHAR(255) NOT NULL,
  source_system VARCHAR(128) NOT NULL,
  source_version VARCHAR(128) NOT NULL,
  site_id VARCHAR(128) NOT NULL,
  device_id VARCHAR(128) NOT NULL,
  alarm_name VARCHAR(255) NULL,
  title VARCHAR(512) NOT NULL,
  symptom_summary TEXT NOT NULL,
  root_cause TEXT NULL,
  action_taken TEXT NULL,
  status VARCHAR(32) NOT NULL,
  verified BOOLEAN NOT NULL,
  approval_id CHAR(36) NULL,
  payload_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  canonicalization_version SMALLINT UNSIGNED NOT NULL,
  closed_at DATETIME(6) NULL,
  created_at DATETIME(6) NOT NULL,
  updated_at DATETIME(6) NOT NULL,
  CONSTRAINT pk_work_order PRIMARY KEY (tenant_id, ticket_id),
  CONSTRAINT fk_work_order_device FOREIGN KEY (tenant_id, device_id) REFERENCES asset_device (tenant_id, device_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
  CONSTRAINT uq_work_order_source UNIQUE (tenant_id, source_system, ticket_id, source_version),
  CONSTRAINT ck_work_order_canonical CHECK (canonicalization_version = 2),
  INDEX ix_work_order_search (tenant_id, device_id, alarm_name, status),
  INDEX ix_work_order_verified (tenant_id, verified, closed_at)
) ENGINE=InnoDB DEFAULT CHARACTER SET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE work_order_outbox (
  event_id CHAR(36) NOT NULL,
  tenant_id VARCHAR(64) NOT NULL,
  ticket_id VARCHAR(255) NOT NULL,
  source_version VARCHAR(128) NOT NULL,
  event_type VARCHAR(128) NOT NULL,
  event_version INT UNSIGNED NOT NULL,
  idempotency_key_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  payload_json JSON NOT NULL,
  publish_state VARCHAR(24) NOT NULL,
  attempt_count INT UNSIGNED NOT NULL,
  available_at DATETIME(6) NOT NULL,
  published_at DATETIME(6) NULL,
  created_at DATETIME(6) NOT NULL,
  CONSTRAINT pk_work_order_outbox PRIMARY KEY (event_id),
  CONSTRAINT fk_work_order_outbox_order FOREIGN KEY (tenant_id, ticket_id) REFERENCES work_order (tenant_id, ticket_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
  CONSTRAINT uq_work_order_outbox_idempotency UNIQUE (idempotency_key_hash),
  INDEX ix_work_order_outbox_pending (publish_state, available_at)
) ENGINE=InnoDB DEFAULT CHARACTER SET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE ops_write_audit (
  audit_id CHAR(36) NOT NULL,
  tenant_id VARCHAR(64) NOT NULL,
  actor_id VARCHAR(255) NOT NULL,
  actor_roles JSON NOT NULL,
  action_name VARCHAR(128) NOT NULL,
  resource_type VARCHAR(128) NOT NULL,
  resource_id VARCHAR(255) NOT NULL,
  request_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  result_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  canonicalization_version SMALLINT UNSIGNED NOT NULL,
  trace_id CHAR(36) NOT NULL,
  acceptance_run_id CHAR(36) NOT NULL,
  occurred_at DATETIME(6) NOT NULL,
  CONSTRAINT pk_ops_write_audit PRIMARY KEY (audit_id),
  CONSTRAINT ck_ops_write_audit_canonical CHECK (canonicalization_version = 2),
  INDEX ix_ops_write_audit_resource (tenant_id, resource_type, resource_id, occurred_at),
  INDEX ix_ops_write_audit_trace (trace_id)
) ENGINE=InnoDB DEFAULT CHARACTER SET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
