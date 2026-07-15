from __future__ import annotations

import os
from typing import Any

import pytest

from scripts.migrations.__main__ import connection, verify_schema


def required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        pytest.fail(f"{name} is required for the M1 real-service integration test")
    return value


def database_connection(database: str) -> Any:
    return connection(
        host=required("M1_MYSQL_HOST"),
        port=int(required("M1_MYSQL_PORT")),
        user=required("MYSQL_USER"),
        password=required("MYSQL_PASSWORD"),
        database=database,
    )


@pytest.mark.parametrize(
    ("schema_name", "database_variable"),
    (("control", "M1_CONTROL_DATABASE"), ("ops", "M1_OPS_DATABASE")),
)
def test_real_mysql_schema_matches_committed_manifest(
    schema_name: str, database_variable: str
) -> None:
    with database_connection(required(database_variable)) as db:
        digest = verify_schema(db, schema_name)
        with db.cursor() as cursor:
            cursor.execute(
                "SELECT @@session.time_zone AS time_zone, @@character_set_database AS charset, "
                "@@collation_database AS collation"
            )
            settings = cursor.fetchone()
            cursor.execute(
                "SELECT manifest_digest, canonicalization_version FROM schema_manifest "
                "WHERE schema_name=%s",
                (schema_name,),
            )
            manifest = cursor.fetchone()
    assert settings == {
        "time_zone": "+00:00",
        "charset": "utf8mb4",
        "collation": "utf8mb4_0900_ai_ci",
    }
    assert manifest["manifest_digest"] == digest
    assert manifest["canonicalization_version"] == 2
