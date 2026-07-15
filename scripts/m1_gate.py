#!/usr/bin/env python3
"""Source-exact M1 Gate against real MySQL 8.4 and Redis."""

from __future__ import annotations

import json
import os
import secrets
import signal
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import pymysql
import redis
from pymysql.cursors import DictCursor

from energy_agent.core.canonicalization import canonical_digest
from scripts.m0_gate import junit_counts, uuid7, write_combined_junit
from scripts.migrations.__main__ import (
    MigrationError,
    apply_schema,
    connection,
    migration_set_digest,
    store_revision,
    verify_schema,
)

ROOT = Path(__file__).resolve().parents[1]
VERSIONS_FILE = ROOT / "deploy/versions.env"
LUA_FILE = ROOT / "scripts/migrations/atomic_preflight.lua"


def load_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key] = value
    return values


def random_secret(prefix: str = "m1") -> str:
    return f"{prefix}_{secrets.token_urlsafe(32)}"


def gate_environment(project: str) -> dict[str, str]:
    environment = {
        **os.environ,
        **load_env_file(VERSIONS_FILE),
        "COMPOSE_PROJECT_NAME": project,
        "DEPLOYMENT_PROFILE": "full",
        "MYSQL_HOST_PORT": "0",
        "REDIS_HOST_PORT": "0",
        "MYSQL_ROOT_PASSWORD": random_secret(),
        "MYSQL_DATABASE": "m1_bootstrap",
        "MYSQL_USER": "m1_gate",
        "MYSQL_PASSWORD": random_secret(),
        "REDIS_PASSWORD": random_secret(),
        "RABBITMQ_DEFAULT_USER": "m1_gate",
        "RABBITMQ_DEFAULT_PASS": random_secret(),
        "MINIO_ROOT_USER": "m1gate",
        "MINIO_ROOT_PASSWORD": random_secret(),
        "INFLUXDB_USERNAME": "m1_gate",
        "INFLUXDB_PASSWORD": random_secret(),
        "INFLUXDB_ORG": "m1-gate",
        "INFLUXDB_BUCKET": "m1-gate",
        "INFLUXDB_TOKEN": random_secret(),
        "OPENSEARCH_INITIAL_ADMIN_PASSWORD": "M1a!" + random_secret(),
        "NEO4J_USERNAME": "neo4j",
        "NEO4J_PASSWORD": "M1a!" + random_secret(),
        "KEYCLOAK_ADMIN": "m1-admin",
        "KEYCLOAK_ADMIN_PASSWORD": "M1a!" + random_secret(),
        "KEYCLOAK_M0_REALM": "m0-gate",
        "KEYCLOAK_M0_CLIENT_ID": "m0-gate-client",
        "KEYCLOAK_M0_CLIENT_SECRET": random_secret(),
        "MILVUS_ROOT_PASSWORD": "M1a!" + random_secret(),
        "MODEL_PROVIDER": "",
        "DATA_SOURCE": "",
        "DATABASE_URL": "",
        "RUNTIME_MOCK_PROVIDER": "",
    }
    return environment


def run(
    arguments: list[str],
    *,
    environment: dict[str, str] | None = None,
    capture: bool = False,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        arguments,
        cwd=ROOT,
        env=environment,
        text=True,
        capture_output=capture,
        check=check,
    )


def compose(
    project: str,
    environment: dict[str, str],
    arguments: list[str],
    *,
    capture: bool = False,
) -> str:
    result = run(
        [
            "docker",
            "compose",
            "--env-file",
            str(VERSIONS_FILE),
            "--project-name",
            project,
            "--profile",
            "full",
            *arguments,
        ],
        environment=environment,
        capture=capture,
    )
    return result.stdout if capture else ""


def mapped_port(project: str, environment: dict[str, str], service: str, port: int) -> int:
    output = compose(project, environment, ["port", service, str(port)], capture=True).strip()
    return int(output.rsplit(":", 1)[1])


def root_connection(environment: dict[str, str], mysql_port: int) -> Any:
    return pymysql.connect(
        host="127.0.0.1",
        port=mysql_port,
        user="root",
        password=environment["MYSQL_ROOT_PASSWORD"],
        charset="utf8mb4",
        autocommit=True,
        cursorclass=DictCursor,
    )


def create_database(admin: Any, database: str, user: str) -> None:
    if not database.replace("_", "").isalnum():
        raise RuntimeError("unsafe Gate database name")
    with admin.cursor() as cursor:
        cursor.execute(
            f"CREATE DATABASE `{database}` CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci"
        )
        cursor.execute(f"GRANT ALL PRIVILEGES ON `{database}`.* TO %s@'%%'", (user,))


def mysql_connection(
    environment: dict[str, str], mysql_port: int, database: str
) -> Any:
    return connection(
        host="127.0.0.1",
        port=mysql_port,
        user=environment["MYSQL_USER"],
        password=environment["MYSQL_PASSWORD"],
        database=database,
    )


def validate_counts(counts: dict[str, int]) -> None:
    if counts["tests"] <= 0 or any(counts[key] for key in ("failures", "errors", "skipped")):
        raise RuntimeError(f"M1 Gate requires tests>0 and zero failures/errors/skips: {counts}")


def interrupted_recovery(
    environment: dict[str, str], mysql_port: int, schema_name: str, database: str
) -> dict[str, Any]:
    child_environment = {
        **environment,
        "MYSQL_HOST": "127.0.0.1",
        "MYSQL_PORT": str(mysql_port),
        "M1_MIGRATION_KILL_AFTER_STEP": f"{schema_name}:0001:2",
    }
    killed = run(
        [
            "uv",
            "run",
            "python",
            "-m",
            "scripts.migrations",
            "apply",
            schema_name,
            "--database",
            database,
        ],
        environment=child_environment,
        capture=True,
        check=False,
    )
    if killed.returncode not in {-signal.SIGKILL, 128 + signal.SIGKILL}:
        raise RuntimeError(
            f"migration interruption did not end with SIGKILL: {schema_name} rc={killed.returncode}"
        )
    with mysql_connection(environment, mysql_port, database) as db:
        apply_schema(db, schema_name)
        digest = verify_schema(db, schema_name)
        with db.cursor() as cursor:
            cursor.execute(
                "SELECT status,total_steps,applied_steps FROM schema_migration WHERE version='0001'"
            )
            row = cursor.fetchone()
    if row["status"] != "APPLIED" or row["total_steps"] != row["applied_steps"]:
        raise RuntimeError(f"interrupted migration did not fully recover: {schema_name}")
    return {
        "schema": schema_name,
        "killed_returncode": killed.returncode,
        "recovered_status": row["status"],
        "applied_steps": row["applied_steps"],
        "manifest_digest": digest,
    }


def verify_checksum_refusal(
    environment: dict[str, str], mysql_port: int, schema_name: str, database: str
) -> bool:
    with tempfile.TemporaryDirectory(prefix="m1-checksum-") as directory:
        root = Path(directory)
        target = root / schema_name
        target.mkdir(parents=True)
        source = ROOT / f"migrations/{schema_name}/0001_initial.sql"
        mutated = target / source.name
        mutated.write_bytes(source.read_bytes() + b"\n")
        with mysql_connection(environment, mysql_port, database) as db:
            try:
                apply_schema(db, schema_name, migrations_root=root)
            except MigrationError as error:
                return "checksum changed" in str(error)
    return False


def revision_probe(environment: dict[str, str], mysql_port: int, database: str) -> dict[str, str]:
    session_id = uuid7()
    payload = {"device_id": "device-1", "message": "diagnose"}
    digest = canonical_digest(payload)
    with mysql_connection(environment, mysql_port, database) as db:
        with db.cursor() as cursor:
            cursor.execute(
                "INSERT INTO diagnosis_session_history "
                "(session_id,tenant_id,owner_id,revision,phase,first_retained_sequence,"
                "event_high_watermark,created_at,updated_at) "
                "VALUES (%s,'pilot','operator',1,'INIT',0,0,UTC_TIMESTAMP(6),UTC_TIMESTAMP(6))",
                (session_id,),
            )
        first = store_revision(
            db, session_id=session_id, revision=1, payload_hash=digest, payload=payload
        )
        replay = store_revision(
            db, session_id=session_id, revision=1, payload_hash=digest, payload=payload
        )
        conflict = "NOT_REJECTED"
        try:
            store_revision(
                db,
                session_id=session_id,
                revision=1,
                payload_hash=canonical_digest({**payload, "message": "changed"}),
                payload={**payload, "message": "changed"},
            )
        except MigrationError:
            conflict = "REJECTED"
        with db.cursor() as cursor:
            cursor.execute(
                "SELECT payload_hash FROM diagnosis_revision WHERE session_id=%s AND revision=1",
                (session_id,),
            )
            persisted = cursor.fetchone()["payload_hash"]
    if (first, replay, conflict, persisted) != ("APPLIED", "ALREADY_APPLIED", "REJECTED", digest):
        raise RuntimeError("revision idempotency/conflict probe failed")
    return {
        "first": first,
        "replay": replay,
        "different_hash": conflict,
        "persisted_hash": persisted,
    }


def redis_snapshot(client: Any, keys: list[str]) -> list[tuple[str, bytes | None]]:
    return [(cast(bytes, client.type(key)).decode(), client.dump(key)) for key in keys]


def redis_atomicity_probe(environment: dict[str, str], redis_port: int) -> dict[str, Any]:
    client = redis.Redis(
        host="127.0.0.1",
        port=redis_port,
        password=environment["REDIS_PASSWORD"],
        decode_responses=False,
        socket_timeout=5,
    )
    prefix = f"m1:{uuid7()}"
    keys = [f"{prefix}:session", f"{prefix}:run", f"{prefix}:pending", f"{prefix}:audit"]
    client.delete(*keys)
    client.set(keys[3], b"wrong-type")
    before = redis_snapshot(client, keys)
    script = LUA_FILE.read_text(encoding="utf-8")
    failure = client.eval(script, len(keys), *keys, "1", "run-1", "a" * 64, "0")
    after = redis_snapshot(client, keys)
    if before != after or failure[:2] != [0, b"KEY_TYPE_MISMATCH"]:
        raise RuntimeError("Redis Lua type failure left a partial write")
    client.delete(*keys)
    success = client.eval(script, len(keys), *keys, "1", "run-1", "a" * 64, "0")
    if success[:2] != [1, b"OK"]:
        raise RuntimeError("Redis Lua success path failed")
    return {
        "keys": keys,
        "failure": "KEY_TYPE_MISMATCH",
        "zero_partial_writes": True,
        "success_types": [cast(bytes, client.type(key)).decode() for key in keys],
    }


def service_evidence(project: str, environment: dict[str, str]) -> list[dict[str, str]]:
    evidence: list[dict[str, str]] = []
    for container_id in compose(project, environment, ["ps", "-q"], capture=True).splitlines():
        result = run(
            [
                "docker",
                "inspect",
                "--format",
                "{{.Name}}|{{.Config.Image}}|{{.Image}}",
                container_id,
            ],
            capture=True,
        ).stdout.strip()
        name, configured, image_id = result.split("|", 2)
        evidence.append(
            {"container": name.lstrip("/"), "configured": configured, "image_id": image_id}
        )
    return sorted(evidence, key=lambda item: item["container"])


def assert_cleanup(project: str) -> dict[str, int]:
    label = f"label=com.docker.compose.project={project}"
    queries = {
        "containers": ["docker", "ps", "-aq", "--filter", label],
        "volumes": ["docker", "volume", "ls", "-q", "--filter", label],
        "networks": ["docker", "network", "ls", "-q", "--filter", label],
    }
    remaining = {
        name: len(run(arguments, capture=True).stdout.splitlines())
        for name, arguments in queries.items()
    }
    if any(remaining.values()):
        raise RuntimeError(f"M1 Gate cleanup left resources: {remaining}")
    return remaining


def run_gate() -> Path:
    acceptance_run_id = uuid7()
    artifact_dir = ROOT / "artifacts/gates/M1" / acceptance_run_id
    artifact_dir.mkdir(parents=True)
    started_at = datetime.now(UTC)
    project = f"energy-agent-m1-{acceptance_run_id.replace('-', '')[:12]}"
    environment = gate_environment(project)
    unit_junit = artifact_dir / "unit-junit.xml"
    contract_junit = artifact_dir / "contract-junit.xml"
    integration_junit = artifact_dir / "integration-junit.xml"
    live_junit = artifact_dir / "live-junit.xml"
    commands = ["make gate-m1"]
    commit_sha = "NOT_RECORDED"
    current_step = "initialize"
    stack_started = False
    cleanup_result: dict[str, int] | None = None
    databases: list[str] = []
    previous_handlers = {
        signum: signal.getsignal(signum) for signum in (signal.SIGINT, signal.SIGTERM)
    }

    def stop_on_signal(signum: int, _frame: object) -> None:
        raise SystemExit(128 + signum)

    for signum in previous_handlers:
        signal.signal(signum, stop_on_signal)

    try:
        current_step = "verify clean source tree"
        status = run(
            ["git", "status", "--porcelain", "--untracked-files=all"], capture=True
        ).stdout.strip()
        if status:
            raise RuntimeError("M1 Gate requires a clean source tree")
        commit_sha = run(["git", "rev-parse", "HEAD"], capture=True).stdout.strip()

        for label, arguments in (
            ("make verify-design", ["make", "verify-design"]),
            ("make lint", ["make", "lint"]),
            ("make typecheck", ["make", "typecheck"]),
            (
                f"uv run pytest tests/unit --junitxml={unit_junit.relative_to(ROOT)}",
                ["uv", "run", "pytest", "tests/unit", f"--junitxml={unit_junit}"],
            ),
            (
                f"uv run pytest tests/contract --junitxml={contract_junit.relative_to(ROOT)}",
                ["uv", "run", "pytest", "tests/contract", f"--junitxml={contract_junit}"],
            ),
        ):
            current_step = label
            commands.append(label)
            run(arguments)
        counts = junit_counts([unit_junit, contract_junit])
        validate_counts(counts)

        current_step = "start real MySQL and Redis"
        commands.append("docker compose ... up -d --wait profile-guard mysql redis")
        compose(
            project,
            environment,
            ["up", "-d", "--wait", "--wait-timeout", "180", "profile-guard", "mysql", "redis"],
        )
        stack_started = True
        mysql_port = mapped_port(project, environment, "mysql", 3306)
        redis_port = mapped_port(project, environment, "redis", 6379)

        suffix = acceptance_run_id.replace("-", "")[:12]
        targets = {schema: f"m1_{suffix}_{schema}" for schema in ("control", "ops")}
        interrupted = {schema: f"m1_{suffix}_{schema}_interrupt" for schema in ("control", "ops")}
        databases.extend([*targets.values(), *interrupted.values()])
        with root_connection(environment, mysql_port) as admin:
            for database in databases:
                create_database(admin, database, environment["MYSQL_USER"])

        current_step = "empty install, rerun, manifest, and checksum refusal"
        manifests: dict[str, str] = {}
        interruption_evidence: list[dict[str, Any]] = []
        checksum_refusal: dict[str, bool] = {}
        for schema_name, database in targets.items():
            with mysql_connection(environment, mysql_port, database) as db:
                apply_schema(db, schema_name)
                manifests[schema_name] = verify_schema(db, schema_name)
                apply_schema(db, schema_name)
                if verify_schema(db, schema_name) != manifests[schema_name]:
                    raise RuntimeError(f"idempotent rerun changed {schema_name} manifest")
            interruption_evidence.append(
                interrupted_recovery(
                    environment, mysql_port, schema_name, interrupted[schema_name]
                )
            )
            checksum_refusal[schema_name] = verify_checksum_refusal(
                environment, mysql_port, schema_name, database
            )
        if not all(checksum_refusal.values()):
            raise RuntimeError("migration checksum change was not rejected")

        revision = revision_probe(environment, mysql_port, targets["control"])
        redis_evidence = redis_atomicity_probe(environment, redis_port)

        current_step = "real-service integration and live tests"
        service_test_environment = {
            **environment,
            "M1_MYSQL_HOST": "127.0.0.1",
            "M1_MYSQL_PORT": str(mysql_port),
            "M1_CONTROL_DATABASE": targets["control"],
            "M1_OPS_DATABASE": targets["ops"],
            "M1_REDIS_HOST": "127.0.0.1",
            "M1_REDIS_PORT": str(redis_port),
            "M1_REDIS_TEST_PREFIX": f"m1:test:{acceptance_run_id}",
        }
        integration_command = (
            "uv run pytest tests/integration/test_m1_mysql_migrations.py "
            f"--junitxml={integration_junit.relative_to(ROOT)}"
        )
        live_command = (
            "uv run pytest tests/live/test_m1_redis_atomicity.py "
            f"--junitxml={live_junit.relative_to(ROOT)}"
        )
        commands.extend([integration_command, live_command])
        run(
            [
                "uv",
                "run",
                "pytest",
                "tests/integration/test_m1_mysql_migrations.py",
                f"--junitxml={integration_junit}",
            ],
            environment=service_test_environment,
        )
        run(
            [
                "uv",
                "run",
                "pytest",
                "tests/live/test_m1_redis_atomicity.py",
                f"--junitxml={live_junit}",
            ],
            environment=service_test_environment,
        )
        junit_files = [unit_junit, contract_junit, integration_junit, live_junit]
        counts = junit_counts(junit_files)
        validate_counts(counts)
        write_combined_junit(junit_files, artifact_dir / "junit.xml")

        current_step = "authoritative restart readback"
        mysql_before = dict(manifests)
        compose(project, environment, ["restart", "mysql", "redis"])
        compose(
            project,
            environment,
            ["up", "-d", "--wait", "--wait-timeout", "180", "mysql", "redis"],
        )
        mysql_port = mapped_port(project, environment, "mysql", 3306)
        redis_port = mapped_port(project, environment, "redis", 6379)
        mysql_after: dict[str, str] = {}
        for schema_name, database in targets.items():
            with mysql_connection(environment, mysql_port, database) as db:
                mysql_after[schema_name] = verify_schema(db, schema_name)
        if mysql_after != mysql_before:
            raise RuntimeError("MySQL manifest readback changed after restart")
        redis_client = redis.Redis(
            host="127.0.0.1",
            port=redis_port,
            password=environment["REDIS_PASSWORD"],
            decode_responses=True,
        )
        if redis_client.hget(redis_evidence["keys"][1], "payload_hash") != "a" * 64:
            raise RuntimeError("Redis authoritative readback missing after restart")

        current_step = "drift refusal"
        drift_refusal: dict[str, bool] = {}
        for schema_name, database in targets.items():
            with mysql_connection(environment, mysql_port, database) as db:
                with db.cursor() as cursor:
                    cursor.execute(
                        "ALTER TABLE schema_manifest ADD COLUMN forbidden_drift INT NULL"
                    )
                try:
                    verify_schema(db, schema_name)
                except MigrationError as error:
                    drift_refusal[schema_name] = "drift detected" in str(error)
                else:
                    drift_refusal[schema_name] = False
        if not all(drift_refusal.values()):
            raise RuntimeError("schema drift was not rejected")

        current_step = "write sanitized evidence"
        versions = service_evidence(project, environment)
        with root_connection(environment, mysql_port) as admin, admin.cursor() as cursor:
            cursor.execute("SELECT VERSION() AS version, @@global.time_zone AS time_zone")
            mysql_version = cursor.fetchone()
        redis_version = redis_client.info("server")["redis_version"]
        evidence = {
            "module": "M1",
            "commit_sha": commit_sha,
            "acceptance_run_id": acceptance_run_id,
            "environment": "isolated Docker Compose real MySQL/Redis",
            "test_commands": commands,
            "test_count": counts["tests"],
            "failure_count": counts["failures"] + counts["errors"],
            "skip_count": counts["skipped"],
            "result": "TESTS_PASSED_REVIEW_PENDING",
            "started_at": started_at.isoformat(),
            "finished_at": datetime.now(UTC).isoformat(),
        }
        files: dict[str, Any] = {
            "gate.json": evidence,
            "service_versions.json": {
                "mysql": mysql_version,
                "redis": {"version": redis_version},
            },
            "image_digests.json": versions,
            "migration_checksums.json": {
                schema: migration_set_digest(schema) for schema in ("control", "ops")
            },
            "schema_manifests.json": manifests,
            "readback_hashes.json": {
                "mysql_before_restart": mysql_before,
                "mysql_after_restart": mysql_after,
                "revision": revision,
                "redis_payload_hash": "a" * 64,
            },
            "interruption_recovery.json": interruption_evidence,
            "redis_atomicity.json": redis_evidence,
            "negative_paths.json": {
                "checksum_refusal": checksum_refusal,
                "drift_refusal": drift_refusal,
            },
            "review.md": "# M1 independent review\n\nPending source-exact read-only review.\n",
        }
        for filename, value in files.items():
            path = artifact_dir / filename
            if isinstance(value, str):
                path.write_text(value, encoding="utf-8")
            else:
                path.write_text(
                    json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
                )
        run(["make", "verify-design"])
        print(f"OK: M1 Gate passed with acceptance_run_id={acceptance_run_id}")
        return artifact_dir
    except BaseException as error:
        failure = {
            "module": "M1",
            "commit_sha": commit_sha,
            "acceptance_run_id": acceptance_run_id,
            "result": "FAILED",
            "failed_step": current_step,
            "error_type": type(error).__name__,
            "started_at": started_at.isoformat(),
            "finished_at": datetime.now(UTC).isoformat(),
        }
        (artifact_dir / "gate.json").write_text(
            json.dumps(failure, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        raise
    finally:
        if stack_started:
            try:
                compose(project, environment, ["down", "--volumes", "--remove-orphans"])
                cleanup_result = assert_cleanup(project)
            except Exception as cleanup_error:  # noqa: BLE001 - preserve original Gate error
                print(f"ERROR: M1 cleanup failed: {cleanup_error}", file=sys.stderr)
                if sys.exc_info()[0] is None:
                    raise
        if cleanup_result is not None:
            (artifact_dir / "cleanup.json").write_text(
                json.dumps(cleanup_result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
        for signum, handler in previous_handlers.items():
            signal.signal(signum, handler)


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    if arguments != ["gate"]:
        print("usage: python -m scripts.m1_gate gate", file=sys.stderr)
        return 2
    run_gate()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
