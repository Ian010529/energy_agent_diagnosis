"""Apply and verify the M1 MySQL schemas."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import signal
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import pymysql
from pymysql.cursors import DictCursor

from energy_agent.core.canonicalization import CANONICALIZATION_VERSION, canonical_digest

ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS_ROOT = ROOT / "migrations"
DESCRIPTOR_ROOT = ROOT / "schema/descriptor"
SCHEMAS = ("control", "ops")
CREATE_TABLE_PATTERN = re.compile(r"^CREATE\s+TABLE\s+`?([a-zA-Z0-9_]+)`?", re.IGNORECASE)

BOOTSTRAP_SQL = (
    """
    CREATE TABLE schema_migration (
      version VARCHAR(64) NOT NULL,
      filename VARCHAR(255) NOT NULL,
      migration_checksum CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
      status VARCHAR(16) NOT NULL,
      total_steps INT UNSIGNED NOT NULL,
      applied_steps INT UNSIGNED NOT NULL,
      started_at DATETIME(6) NOT NULL,
      finished_at DATETIME(6) NULL,
      CONSTRAINT pk_schema_migration PRIMARY KEY (version),
      CONSTRAINT uq_schema_migration_filename UNIQUE (filename),
      CONSTRAINT ck_schema_migration_status CHECK (status IN ('RUNNING','APPLIED','FAILED')),
      CONSTRAINT ck_schema_migration_steps CHECK (applied_steps <= total_steps)
    ) ENGINE=InnoDB DEFAULT CHARACTER SET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
    """,
    """
    CREATE TABLE schema_migration_step (
      version VARCHAR(64) NOT NULL,
      step_no INT UNSIGNED NOT NULL,
      object_type VARCHAR(32) NOT NULL,
      object_name VARCHAR(128) NOT NULL,
      statement_checksum CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
      applied_at DATETIME(6) NOT NULL,
      CONSTRAINT pk_schema_migration_step PRIMARY KEY (version, step_no),
      CONSTRAINT fk_schema_migration_step_version FOREIGN KEY (version)
        REFERENCES schema_migration (version) ON UPDATE RESTRICT ON DELETE RESTRICT,
      CONSTRAINT uq_schema_migration_step_object UNIQUE (version, object_type, object_name)
    ) ENGINE=InnoDB DEFAULT CHARACTER SET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
    """,
)


class MigrationError(RuntimeError):
    """Migration checksum, schema drift, or state conflict."""


def utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def split_statements(source: str) -> list[str]:
    statements = [statement.strip() for statement in source.split(";") if statement.strip()]
    if not statements or any(not CREATE_TABLE_PATTERN.match(statement) for statement in statements):
        raise MigrationError("M1 migrations may contain only CREATE TABLE statements")
    return statements


def migration_files(schema_name: str, root: Path = MIGRATIONS_ROOT) -> list[Path]:
    files = sorted((root / schema_name).glob("[0-9][0-9][0-9][0-9]_*.sql"))
    if not files or files[0].name[:4] != "0001":
        raise MigrationError(f"{schema_name} migrations must start at 0001")
    return files


def migration_set_digest(schema_name: str, root: Path = MIGRATIONS_ROOT) -> str:
    entries = [
        {"filename": path.name, "sha256": sha256_bytes(path.read_bytes())}
        for path in migration_files(schema_name, root)
    ]
    return canonical_digest(entries)


@contextmanager
def connection(
    *, host: str, port: int, user: str, password: str, database: str
) -> Iterator[Any]:
    value: Any = pymysql.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        database=database,
        charset="utf8mb4",
        autocommit=True,
        cursorclass=DictCursor,
    )
    try:
        with value.cursor() as cursor:
            cursor.execute("SET time_zone = '+00:00'")
        yield value
    finally:
        value.close()


def table_exists(db: Any, table_name: str) -> bool:
    with db.cursor() as cursor:
        cursor.execute(
            "SELECT COUNT(*) AS count FROM information_schema.tables "
            "WHERE table_schema=DATABASE() AND table_name=%s AND table_type='BASE TABLE'",
            (table_name,),
        )
        return cast(int, cursor.fetchone()["count"]) == 1


def ensure_bootstrap(db: Any) -> None:
    for statement in BOOTSTRAP_SQL:
        match = CREATE_TABLE_PATTERN.match(statement.strip())
        if match is None:
            raise MigrationError("invalid bootstrap statement")
        if not table_exists(db, match.group(1)):
            with db.cursor() as cursor:
                cursor.execute(statement)


def _rows(db: Any, sql: str) -> list[dict[str, Any]]:
    with db.cursor() as cursor:
        cursor.execute(sql)
        return list(cursor.fetchall())


def _clean_row(row: dict[str, Any]) -> dict[str, Any]:
    return {key.lower(): value for key, value in row.items()}


def introspect_descriptor(db: Any, schema_name: str) -> dict[str, Any]:
    tables = _rows(
        db,
        "SELECT TABLE_NAME, ENGINE, TABLE_COLLATION FROM information_schema.TABLES "
        "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_TYPE='BASE TABLE' ORDER BY TABLE_NAME",
    )
    columns = _rows(
        db,
        "SELECT TABLE_NAME, ORDINAL_POSITION, COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, "
        "COLUMN_DEFAULT, EXTRA, CHARACTER_SET_NAME, COLLATION_NAME, GENERATION_EXPRESSION "
        "FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() "
        "ORDER BY TABLE_NAME, ORDINAL_POSITION",
    )
    indexes = _rows(
        db,
        "SELECT TABLE_NAME, INDEX_NAME, NON_UNIQUE, SEQ_IN_INDEX, COLUMN_NAME, SUB_PART, "
        "COLLATION, INDEX_TYPE, IS_VISIBLE, EXPRESSION FROM information_schema.STATISTICS "
        "WHERE TABLE_SCHEMA=DATABASE() ORDER BY TABLE_NAME, INDEX_NAME, SEQ_IN_INDEX",
    )
    constraints = _rows(
        db,
        "SELECT TABLE_NAME, CONSTRAINT_NAME, CONSTRAINT_TYPE FROM "
        "information_schema.TABLE_CONSTRAINTS WHERE CONSTRAINT_SCHEMA=DATABASE() "
        "ORDER BY TABLE_NAME, CONSTRAINT_NAME",
    )
    checks = _rows(
        db,
        "SELECT tc.TABLE_NAME, cc.CONSTRAINT_NAME, cc.CHECK_CLAUSE "
        "FROM information_schema.TABLE_CONSTRAINTS tc JOIN information_schema.CHECK_CONSTRAINTS cc "
        "ON cc.CONSTRAINT_SCHEMA=tc.CONSTRAINT_SCHEMA AND cc.CONSTRAINT_NAME=tc.CONSTRAINT_NAME "
        "WHERE tc.CONSTRAINT_SCHEMA=DATABASE() AND tc.CONSTRAINT_TYPE='CHECK' "
        "ORDER BY tc.TABLE_NAME, cc.CONSTRAINT_NAME",
    )
    foreign_keys = _rows(
        db,
        "SELECT k.TABLE_NAME, k.CONSTRAINT_NAME, k.ORDINAL_POSITION, k.COLUMN_NAME, "
        "k.REFERENCED_TABLE_NAME, k.REFERENCED_COLUMN_NAME, r.UPDATE_RULE, r.DELETE_RULE "
        "FROM information_schema.KEY_COLUMN_USAGE k JOIN "
        "information_schema.REFERENTIAL_CONSTRAINTS r "
        "ON r.CONSTRAINT_SCHEMA=k.CONSTRAINT_SCHEMA AND r.CONSTRAINT_NAME=k.CONSTRAINT_NAME "
        "WHERE k.CONSTRAINT_SCHEMA=DATABASE() AND k.REFERENCED_TABLE_NAME IS NOT NULL "
        "ORDER BY k.TABLE_NAME, k.CONSTRAINT_NAME, k.ORDINAL_POSITION",
    )
    return {
        "schema": schema_name,
        "canonicalization_version": CANONICALIZATION_VERSION,
        "tables": [_clean_row(row) for row in tables],
        "columns": [_clean_row(row) for row in columns],
        "indexes": [_clean_row(row) for row in indexes],
        "constraints": [_clean_row(row) for row in constraints],
        "checks": [_clean_row(row) for row in checks],
        "foreign_keys": [_clean_row(row) for row in foreign_keys],
    }


def load_expected_descriptor(schema_name: str, root: Path = DESCRIPTOR_ROOT) -> dict[str, Any]:
    path = root / f"{schema_name}-v1.json"
    if not path.exists():
        raise MigrationError(f"missing committed schema descriptor: {path}")
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def assert_expected_table(db: Any, schema_name: str, table_name: str) -> None:
    expected = load_expected_descriptor(schema_name)
    actual = introspect_descriptor(db, schema_name)
    for section in ("tables", "columns", "indexes", "constraints", "checks", "foreign_keys"):
        expected_rows = [row for row in expected[section] if row["table_name"] == table_name]
        actual_rows = [row for row in actual[section] if row["table_name"] == table_name]
        if expected_rows != actual_rows:
            raise MigrationError(
                f"schema drift detected for {schema_name}.{table_name} in {section}"
            )


def apply_schema(
    db: Any,
    schema_name: str,
    *,
    migrations_root: Path = MIGRATIONS_ROOT,
) -> None:
    ensure_bootstrap(db)
    lock_name = f"energy-agent-migrate:{schema_name}"
    with db.cursor() as cursor:
        cursor.execute("SELECT GET_LOCK(%s, 30) AS acquired", (lock_name,))
        if cursor.fetchone()["acquired"] != 1:
            raise MigrationError(f"could not acquire migration lock for {schema_name}")
    try:
        for path in migration_files(schema_name, migrations_root):
            apply_migration(db, schema_name, path)
        install_manifest(db, schema_name, migrations_root=migrations_root)
    finally:
        with db.cursor() as cursor:
            cursor.execute("SELECT RELEASE_LOCK(%s)", (lock_name,))


def apply_migration(db: Any, schema_name: str, path: Path) -> None:
    version = path.name.split("_", 1)[0]
    migration_checksum = sha256_bytes(path.read_bytes())
    statements = split_statements(path.read_text(encoding="utf-8"))
    with db.cursor() as cursor:
        cursor.execute("SELECT * FROM schema_migration WHERE version=%s", (version,))
        existing = cursor.fetchone()
        if existing and existing["migration_checksum"] != migration_checksum:
            raise MigrationError(f"migration checksum changed: {path.name}")
        if existing and existing["status"] == "APPLIED":
            return
        if existing is None:
            cursor.execute(
                "INSERT INTO schema_migration "
                "(version,filename,migration_checksum,status,total_steps,applied_steps,started_at) "
                "VALUES (%s,%s,%s,'RUNNING',%s,0,%s)",
                (version, path.name, migration_checksum, len(statements), utc_now()),
            )

    for index, statement in enumerate(statements, start=1):
        match = CREATE_TABLE_PATTERN.match(statement)
        if match is None:
            raise MigrationError("unsupported migration statement")
        table_name = match.group(1)
        statement_checksum = sha256_bytes(statement.encode())
        with db.cursor() as cursor:
            cursor.execute(
                "SELECT statement_checksum FROM schema_migration_step "
                "WHERE version=%s AND step_no=%s",
                (version, index),
            )
            step = cursor.fetchone()
        if step:
            if step["statement_checksum"] != statement_checksum:
                raise MigrationError(f"migration step checksum changed: {path.name} step {index}")
            assert_expected_table(db, schema_name, table_name)
            continue
        if table_exists(db, table_name):
            assert_expected_table(db, schema_name, table_name)
        else:
            with db.cursor() as cursor:
                cursor.execute(statement)
        fail_after = os.getenv("M1_MIGRATION_KILL_AFTER_STEP")
        if fail_after == f"{schema_name}:{version}:{index}":
            os.kill(os.getpid(), signal.SIGKILL)
        assert_expected_table(db, schema_name, table_name)
        with db.cursor() as cursor:
            cursor.execute(
                "INSERT INTO schema_migration_step "
                "(version,step_no,object_type,object_name,statement_checksum,applied_at) "
                "VALUES (%s,%s,'TABLE',%s,%s,%s)",
                (version, index, table_name, statement_checksum, utc_now()),
            )
            cursor.execute(
                "UPDATE schema_migration SET applied_steps=%s WHERE version=%s",
                (index, version),
            )
    with db.cursor() as cursor:
        cursor.execute(
            "UPDATE schema_migration SET status='APPLIED', "
            "applied_steps=total_steps, finished_at=%s "
            "WHERE version=%s",
            (utc_now(), version),
        )


def _expected_actual_descriptor(
    db: Any, schema_name: str
) -> tuple[dict[str, Any], str]:
    expected = load_expected_descriptor(schema_name)
    actual = introspect_descriptor(db, schema_name)
    if actual != expected:
        raise MigrationError(f"schema drift detected for {schema_name}")
    return actual, canonical_digest(actual)


def _validate_manifest_row(
    row: dict[str, Any],
    *,
    schema_name: str,
    descriptor: dict[str, Any],
    descriptor_digest: str,
    set_digest: str,
) -> None:
    stored_descriptor = row["descriptor_json"]
    if isinstance(stored_descriptor, str):
        stored_descriptor = json.loads(stored_descriptor)
    if (
        row["canonicalization_version"] != 2
        or row["migration_set_digest"] != set_digest
        or row["manifest_digest"] != descriptor_digest
        or stored_descriptor != descriptor
    ):
        raise MigrationError(f"stored schema manifest mismatch for {schema_name}")


def install_manifest(
    db: Any,
    schema_name: str,
    *,
    migrations_root: Path = MIGRATIONS_ROOT,
) -> str:
    actual, descriptor_digest = _expected_actual_descriptor(db, schema_name)
    set_digest = migration_set_digest(schema_name, migrations_root)
    with db.cursor() as cursor:
        cursor.execute("SELECT * FROM schema_manifest WHERE schema_name=%s", (schema_name,))
        row = cursor.fetchone()
        if row is None:
            cursor.execute(
                "INSERT INTO schema_manifest "
                "(schema_name,manifest_version,canonicalization_version,migration_set_digest," 
                "manifest_digest,descriptor_json,created_at) VALUES (%s,1,2,%s,%s,%s,%s)",
                (schema_name, set_digest, descriptor_digest, json.dumps(actual), utc_now()),
            )
            cursor.execute(
                "SELECT * FROM schema_manifest WHERE schema_name=%s", (schema_name,)
            )
            row = cursor.fetchone()
    _validate_manifest_row(
        row,
        schema_name=schema_name,
        descriptor=actual,
        descriptor_digest=descriptor_digest,
        set_digest=set_digest,
    )
    return descriptor_digest


def verify_schema(
    db: Any,
    schema_name: str,
    *,
    migrations_root: Path = MIGRATIONS_ROOT,
) -> str:
    actual, descriptor_digest = _expected_actual_descriptor(db, schema_name)
    set_digest = migration_set_digest(schema_name, migrations_root)
    with db.cursor() as cursor:
        cursor.execute("SELECT * FROM schema_manifest WHERE schema_name=%s", (schema_name,))
        row = cursor.fetchone()
    if row is None:
        raise MigrationError(f"schema manifest is missing for {schema_name}")
    _validate_manifest_row(
        row,
        schema_name=schema_name,
        descriptor=actual,
        descriptor_digest=descriptor_digest,
        set_digest=set_digest,
    )
    return descriptor_digest


def store_revision(
    db: Any,
    *,
    session_id: str,
    revision: int,
    payload_hash: str,
    payload: dict[str, Any],
) -> str:
    with db.cursor() as cursor:
        cursor.execute(
            "SELECT payload_hash FROM diagnosis_revision WHERE session_id=%s AND revision=%s",
            (session_id, revision),
        )
        row = cursor.fetchone()
        if row:
            if row["payload_hash"] != payload_hash:
                raise MigrationError("same revision has a different payload hash")
            return "ALREADY_APPLIED"
        cursor.execute(
            "INSERT INTO diagnosis_revision "
            "(session_id,revision,payload_hash,canonicalization_version,payload_json,created_at) "
            "VALUES (%s,%s,%s,2,%s,%s)",
            (session_id, revision, payload_hash, json.dumps(payload), utc_now()),
        )
    return "APPLIED"


def write_snapshot(db: Any, schema_name: str) -> Path:
    descriptor = introspect_descriptor(db, schema_name)
    DESCRIPTOR_ROOT.mkdir(parents=True, exist_ok=True)
    path = DESCRIPTOR_ROOT / f"{schema_name}-v1.json"
    path.write_text(json.dumps(descriptor, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def command(args: argparse.Namespace) -> int:
    with connection(
        host=args.host,
        port=args.port,
        user=args.user,
        password=args.password,
        database=args.database,
    ) as db:
        if args.action == "apply":
            apply_schema(db, args.schema)
        elif args.action == "verify":
            verify_schema(db, args.schema)
        elif args.action == "snapshot":
            write_snapshot(db, args.schema)
        else:
            raise MigrationError(f"unknown action: {args.action}")
    print(f"OK: {args.action} {args.schema} schema")
    return 0


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser()
    value.add_argument("action", choices=("apply", "verify", "snapshot"))
    value.add_argument("schema", choices=SCHEMAS)
    value.add_argument("--host", default=os.getenv("MYSQL_HOST", "127.0.0.1"))
    value.add_argument("--port", type=int, default=int(os.getenv("MYSQL_PORT", "3306")))
    value.add_argument("--user", default=os.getenv("MYSQL_USER", "energy_agent"))
    value.add_argument("--password", default=os.getenv("MYSQL_PASSWORD", ""))
    value.add_argument("--database", required=True)
    return value


def main(argv: Sequence[str] | None = None) -> int:
    return command(parser().parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
