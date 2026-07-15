from __future__ import annotations

import re
from pathlib import Path

from scripts.migrations.__main__ import migration_set_digest, split_statements

ROOT = Path(__file__).resolve().parents[2]

CONTROL_TABLES = {
    "schema_manifest",
    "auth_scope_binding",
    "diagnosis_session_history",
    "diagnosis_acceptance_receipt",
    "diagnosis_revision",
    "diagnosis_run_history",
    "diagnosis_event_history",
    "diagnosis_tool_audit",
    "diagnosis_approval",
    "diagnosis_approval_audit",
    "diagnosis_approval_outbox",
    "diagnosis_confirmation_token",
    "diagnosis_case",
    "diagnosis_case_review",
    "diagnosis_case_outbox",
    "diagnosis_model_call_attempt",
    "diagnosis_model_settlement",
    "diagnosis_index_release_pointer",
    "expert_template",
    "manual_review_record",
    "trace_outbox",
    "import_ledger",
}
OPS_TABLES = {
    "schema_manifest",
    "asset_device",
    "asset_hierarchy",
    "enterprise_id_mapping",
    "alarm_event_version",
    "alarm_delivery",
    "alarm_diagnosis_outbox",
    "telemetry_metric_catalog",
    "work_order",
    "work_order_outbox",
    "ops_write_audit",
}


def table_names(schema: str) -> set[str]:
    source = (ROOT / f"migrations/{schema}/0001_initial.sql").read_text(encoding="utf-8")
    return {
        re.match(r"CREATE TABLE ([a-z0-9_]+)", statement, re.IGNORECASE).group(1)  # type: ignore[union-attr]
        for statement in split_statements(source)
    }


def test_greenfield_migrations_cover_all_declared_tables() -> None:
    assert table_names("control") == CONTROL_TABLES
    assert table_names("ops") == OPS_TABLES


def test_migrations_are_frozen_from_0001_and_have_stable_digests() -> None:
    for schema in ("control", "ops"):
        files = sorted((ROOT / "migrations" / schema).glob("*.sql"))
        assert [path.name for path in files] == ["0001_initial.sql"]
        assert re.fullmatch(r"[0-9a-f]{64}", migration_set_digest(schema))


def test_audit_revision_attempt_and_outbox_fks_never_cascade_delete() -> None:
    sources = "\n".join(
        (ROOT / f"migrations/{schema}/0001_initial.sql").read_text(encoding="utf-8")
        for schema in ("control", "ops")
    )
    assert "ON DELETE CASCADE" not in sources.upper()
    assert "ENGINE=InnoDB" in sources
    assert "utf8mb4_0900_ai_ci" in sources
    assert "DATETIME(6)" in sources


def test_every_business_table_with_a_persisted_hash_binds_canonicalization_v2() -> None:
    for schema in ("control", "ops"):
        source = (ROOT / f"migrations/{schema}/0001_initial.sql").read_text(encoding="utf-8")
        for statement in split_statements(source):
            if "_hash CHAR(64)" in statement:
                assert "canonicalization_version SMALLINT UNSIGNED NOT NULL" in statement
                assert "canonicalization_version = 2" in statement


def test_redis_lua_checks_every_key_before_first_write() -> None:
    source = (ROOT / "scripts/migrations/atomic_preflight.lua").read_text(encoding="utf-8")
    operations = ('redis.call("HSET"', 'redis.call("ZADD"')
    first_write = min(source.index(operation) for operation in operations)
    preflight = source[:first_write]
    assert 'redis.call("TYPE", key)' in preflight
    assert "for index, key in ipairs(KEYS)" in preflight
    assert "KEY_TYPE_MISMATCH" in preflight
