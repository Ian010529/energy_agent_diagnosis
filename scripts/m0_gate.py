#!/usr/bin/env python3
"""M0 real-service readiness, persistence, and gate orchestration."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import random
import subprocess
import time
import uuid
import xml.etree.ElementTree as ET
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import httpx
import pika
import pymysql
import redis
from influxdb_client import InfluxDBClient, Point, WriteOptions  # type: ignore[attr-defined]
from minio import Minio
from neo4j import Driver, GraphDatabase
from opensearchpy import OpenSearch
from pymilvus import (
    Collection,
    CollectionSchema,
    DataType,
    FieldSchema,
    connections,
    utility,
)

from scripts.prepare_milvus_config import write_config
from scripts.validate_profile import validate as validate_profile
from scripts.verify_immutable_design import verify

ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT / ".env.m0"
VERSIONS_FILE = ROOT / "deploy/versions.env"
COMPOSE_SERVICES = (
    "mysql",
    "redis",
    "rabbitmq",
    "minio",
    "influxdb",
    "opensearch",
    "etcd",
    "milvus",
    "neo4j",
    "keycloak",
    "toxiproxy",
)
PERSISTENCE_SERVICES = (
    "mysql",
    "redis",
    "rabbitmq",
    "minio",
    "influxdb",
    "opensearch",
    "etcd",
    "milvus",
    "neo4j",
    "keycloak",
    "toxiproxy",
)


def load_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key] = value
    return values


def command(
    arguments: list[str],
    *,
    environment: dict[str, str] | None = None,
    capture: bool = False,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        arguments,
        cwd=ROOT,
        env=environment,
        check=True,
        text=True,
        capture_output=capture,
    )


def compose(
    arguments: list[str],
    environment: dict[str, str],
    *,
    capture: bool = False,
    profile: str = "full",
) -> str:
    result = command(
        [
            "docker",
            "compose",
            "--env-file",
            str(VERSIONS_FILE),
            "--env-file",
            str(ENV_FILE),
            "--profile",
            profile,
            *arguments,
        ],
        environment=environment,
        capture=capture,
    )
    return result.stdout if capture else ""


def uuid7() -> str:
    timestamp_ms = int(time.time() * 1000) & ((1 << 48) - 1)
    random_bits = random.SystemRandom().getrandbits(74)
    value = timestamp_ms << 80
    value |= 0x7 << 76
    value |= ((random_bits >> 62) & 0xFFF) << 64
    value |= 0b10 << 62
    value |= random_bits & ((1 << 62) - 1)
    return str(uuid.UUID(int=value))


def wait_for(label: str, check: Callable[[], None], timeout: float = 300.0) -> None:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            check()
            print(f"OK: {label} ready")
            return
        except Exception as error:  # noqa: BLE001 - readiness retries heterogeneous clients
            last_error = error
            time.sleep(3)
    raise RuntimeError(f"{label} did not become ready: {last_error}")


class M0Probe:
    def __init__(self, settings: dict[str, str], acceptance_run_id: str) -> None:
        self.settings = settings
        self.acceptance_run_id = acceptance_run_id
        self.payload = f"m0-persistence:{acceptance_run_id}".encode()
        self.payload_hash = hashlib.sha256(self.payload).hexdigest()
        self.rabbit_queue = f"m0_gate_{acceptance_run_id.replace('-', '')}"
        self.http = httpx.Client(trust_env=False)

    def mysql(self) -> pymysql.Connection:
        return pymysql.connect(
            host="127.0.0.1",
            port=13306,
            user=self.settings["MYSQL_USER"],
            password=self.settings["MYSQL_PASSWORD"],
            database=self.settings["MYSQL_DATABASE"],
            autocommit=True,
        )

    def redis(self, port: int = 16379) -> redis.Redis:
        return cast(
            redis.Redis,
            redis.Redis(
                host="127.0.0.1",
                port=port,
                password=self.settings["REDIS_PASSWORD"],
                decode_responses=True,
                socket_timeout=5,
            ),
        )

    def rabbit(self) -> pika.BlockingConnection:
        credentials = pika.PlainCredentials(
            self.settings["RABBITMQ_DEFAULT_USER"],
            self.settings["RABBITMQ_DEFAULT_PASS"],
        )
        return pika.BlockingConnection(
            pika.ConnectionParameters(
                host="127.0.0.1", port=15673, credentials=credentials, heartbeat=30
            )
        )

    def minio(self) -> Minio:
        return Minio(
            "127.0.0.1:19000",
            access_key=self.settings["MINIO_ROOT_USER"],
            secret_key=self.settings["MINIO_ROOT_PASSWORD"],
            secure=False,
        )

    def influx(self) -> InfluxDBClient:
        return InfluxDBClient(
            url="http://127.0.0.1:18086",
            token=self.settings["INFLUXDB_TOKEN"],
            org=self.settings["INFLUXDB_ORG"],
            timeout=10_000,
        )

    def opensearch(self) -> OpenSearch:
        return OpenSearch(
            hosts=[{"host": "127.0.0.1", "port": 19200}],
            http_auth=("admin", self.settings["OPENSEARCH_INITIAL_ADMIN_PASSWORD"]),
            use_ssl=False,
            verify_certs=False,
            timeout=30,
        )

    def neo4j(self) -> Driver:
        return GraphDatabase.driver(
            "bolt://127.0.0.1:17687",
            auth=(self.settings["NEO4J_USERNAME"], self.settings["NEO4J_PASSWORD"]),
        )

    def connect_milvus(self) -> None:
        connections.connect(
            alias="m0",
            host="127.0.0.1",
            port="19530",
            user="root",
            password=self.settings["MILVUS_ROOT_PASSWORD"],
            timeout=10,
        )

    def readiness(
        self, environment: dict[str, str], services: tuple[str, ...] | None = None
    ) -> None:
        def mysql_check() -> None:
            with self.mysql() as connection, connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                if cursor.fetchone() != (1,):
                    raise RuntimeError("unexpected MySQL response")

        def redis_check() -> None:
            client = self.redis()
            if not client.ping():
                raise RuntimeError("Redis PING failed")
            expected = {
                "appendonly": "yes",
                "appendfsync": "always",
                "maxmemory-policy": "noeviction",
            }
            for key, expected_value in expected.items():
                configuration = cast(dict[str, str], client.config_get(key))
                actual = configuration.get(key)
                if actual != expected_value:
                    raise RuntimeError(f"Redis {key}={actual}, expected {expected_value}")

        def rabbit_check() -> None:
            connection = self.rabbit()
            connection.close()

        def minio_check() -> None:
            self.minio().list_buckets()

        def influx_check() -> None:
            with self.influx() as client:
                if client.health().status != "pass":
                    raise RuntimeError("InfluxDB health is not pass")

        def opensearch_check() -> None:
            if not self.opensearch().ping():
                raise RuntimeError("OpenSearch ping failed")

        def milvus_check() -> None:
            self.connect_milvus()
            utility.list_collections(using="m0")
            connections.disconnect("m0")

        def neo4j_check() -> None:
            with self.neo4j() as driver:
                driver.verify_connectivity()

        def keycloak_check() -> None:
            response = self.http.get(
                "http://127.0.0.1:18080/realms/master/.well-known/openid-configuration",
                timeout=5,
            )
            response.raise_for_status()

        def toxiproxy_check() -> None:
            response = self.http.get("http://127.0.0.1:18474/version", timeout=5)
            response.raise_for_status()

        checks = {
            "mysql": mysql_check,
            "redis": redis_check,
            "rabbitmq": rabbit_check,
            "minio": minio_check,
            "influxdb": influx_check,
            "opensearch": opensearch_check,
            "milvus": milvus_check,
            "neo4j": neo4j_check,
            "keycloak": keycloak_check,
            "toxiproxy": toxiproxy_check,
        }
        selected = set(services) if services is not None else set(checks) | {"etcd"}
        for name, check in checks.items():
            if name in selected:
                wait_for(name, check)

        if "etcd" in selected:
            compose(
                ["exec", "-T", "etcd", "etcdctl", "endpoint", "health"], environment
            )
            print("OK: etcd ready (Milvus supporting persistence service)")

    def write(self) -> None:
        self._write_mysql()
        self._write_redis()
        self._write_rabbitmq()
        self._write_minio()
        self._write_influxdb()
        self._write_opensearch()
        self._write_milvus()
        self._write_neo4j()
        self._write_keycloak()
        self._write_toxiproxy()

    def readback(self, services: tuple[str, ...] | None = None) -> dict[str, str]:
        readers = {
            "mysql": self._read_mysql,
            "redis": self._read_redis,
            "rabbitmq": self._read_rabbitmq,
            "minio": self._read_minio,
            "influxdb": self._read_influxdb,
            "opensearch": self._read_opensearch,
            "milvus": self._read_milvus,
            "neo4j": self._read_neo4j,
            "keycloak": self._read_keycloak,
            "toxiproxy": self._read_toxiproxy,
        }
        selected = set(services) if services is not None else set(readers)
        readbacks: dict[str, str] = {}
        for service, reader in readers.items():
            if service in selected:
                readbacks[service] = self._read_with_retry(service, reader)
                print(f"OK: {service} persistent readback verified")
        return readbacks

    def _read_with_retry(self, service: str, reader: Callable[[], str]) -> str:
        result: str | None = None

        def check() -> None:
            nonlocal result
            result = reader()
            if result != self.payload_hash:
                raise RuntimeError(f"{service} hash differs from the written payload hash")

        wait_for(f"{service} persistent readback", check, timeout=180)
        if result is None:
            raise RuntimeError(f"{service} readback produced no result")
        return result

    def _write_mysql(self) -> None:
        with self.mysql() as connection, connection.cursor() as cursor:
            cursor.execute(
                "CREATE TABLE IF NOT EXISTS m0_gate ("
                "acceptance_run_id VARCHAR(36) PRIMARY KEY, payload_hash CHAR(64) NOT NULL)"
            )
            cursor.execute(
                "INSERT INTO m0_gate (acceptance_run_id, payload_hash) VALUES (%s, %s) "
                "ON DUPLICATE KEY UPDATE payload_hash=VALUES(payload_hash)",
                (self.acceptance_run_id, self.payload_hash),
            )

    def _read_mysql(self) -> str:
        with self.mysql() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT payload_hash FROM m0_gate WHERE acceptance_run_id=%s",
                (self.acceptance_run_id,),
            )
            row = cursor.fetchone()
        if row is None:
            raise RuntimeError("MySQL row missing")
        return str(row[0])

    def _write_redis(self) -> None:
        self.redis().set(f"m0:gate:{self.acceptance_run_id}", self.payload_hash)

    def _read_redis(self) -> str:
        value = cast(str | None, self.redis().get(f"m0:gate:{self.acceptance_run_id}"))
        if value is None:
            raise RuntimeError("Redis value missing")
        return value

    def _write_rabbitmq(self) -> None:
        connection = self.rabbit()
        try:
            channel = connection.channel()
            channel.confirm_delivery()
            channel.queue_declare(queue=self.rabbit_queue, durable=True)
            # In Pika 1.3, confirm mode blocks until Basic.Ack and returns None.
            # Basic.Nack and mandatory unroutable messages raise exceptions.
            channel.basic_publish(
                exchange="",
                routing_key=self.rabbit_queue,
                body=self.payload_hash.encode(),
                properties=pika.BasicProperties(delivery_mode=2, content_type="text/plain"),
                mandatory=True,
            )
        finally:
            connection.close()

    def _read_rabbitmq(self) -> str:
        connection = self.rabbit()
        try:
            channel = connection.channel()
            method, _, body = channel.basic_get(queue=self.rabbit_queue, auto_ack=False)
            if method is None or body is None:
                raise RuntimeError("RabbitMQ persistent message missing")
            value = str(body.decode())
            channel.basic_ack(method.delivery_tag)
        finally:
            connection.close()
        return value

    def _write_minio(self) -> None:
        client = self.minio()
        bucket = "m0-gate"
        if not client.bucket_exists(bucket):
            client.make_bucket(bucket)
        client.put_object(
            bucket,
            self.acceptance_run_id,
            io.BytesIO(self.payload),
            length=len(self.payload),
            content_type="application/octet-stream",
        )

    def _read_minio(self) -> str:
        response = self.minio().get_object("m0-gate", self.acceptance_run_id)
        try:
            return hashlib.sha256(response.read()).hexdigest()
        finally:
            response.close()
            response.release_conn()

    def _write_influxdb(self) -> None:
        point = (
            Point("m0_gate")  # type: ignore[no-untyped-call]
            .tag("acceptance_run_id", self.acceptance_run_id)
            .field("payload_hash", self.payload_hash)
        )
        with self.influx() as client:
            writer = client.write_api(write_options=WriteOptions(batch_size=1))
            writer.write(
                bucket=self.settings["INFLUXDB_BUCKET"],
                org=self.settings["INFLUXDB_ORG"],
                record=point,
            )
            writer.close()

    def _read_influxdb(self) -> str:
        query = (
            f'from(bucket: "{self.settings["INFLUXDB_BUCKET"]}") '
            "|> range(start: -24h) "
            '|> filter(fn: (r) => r._measurement == "m0_gate") '
            f'|> filter(fn: (r) => r.acceptance_run_id == "{self.acceptance_run_id}") '
            '|> filter(fn: (r) => r._field == "payload_hash") '
            "|> last()"
        )
        with self.influx() as client:
            tables = client.query_api().query(query, org=self.settings["INFLUXDB_ORG"])
        values = [str(record.get_value()) for table in tables for record in table.records]
        if len(values) != 1:
            raise RuntimeError(f"InfluxDB expected one readback, got {len(values)}")
        return values[0]

    def _write_opensearch(self) -> None:
        client = self.opensearch()
        if not client.indices.exists(index="m0-gate"):
            client.indices.create(index="m0-gate")
        client.index(
            index="m0-gate",
            id=self.acceptance_run_id,
            body={"payload_hash": self.payload_hash},
            refresh="wait_for",
        )

    def _read_opensearch(self) -> str:
        result = self.opensearch().get(index="m0-gate", id=self.acceptance_run_id)
        return str(result["_source"]["payload_hash"])

    def _write_milvus(self) -> None:
        self.connect_milvus()
        try:
            collection_name = "m0_gate"
            if not utility.has_collection(collection_name, using="m0"):
                schema = CollectionSchema(
                    fields=[
                        FieldSchema(
                            name="acceptance_run_id",
                            dtype=DataType.VARCHAR,
                            is_primary=True,
                            max_length=64,
                        ),
                        FieldSchema(name="payload_hash", dtype=DataType.VARCHAR, max_length=64),
                        FieldSchema(name="vector", dtype=DataType.FLOAT_VECTOR, dim=1024),
                    ]
                )
                collection = Collection(collection_name, schema=schema, using="m0")
                collection.create_index(
                    "vector",
                    {"index_type": "HNSW", "metric_type": "COSINE", "params": {"M": 8}},
                )
            collection = Collection(collection_name, using="m0")
            vector = [0.0] * 1024
            vector[0] = 1.0
            collection.upsert(
                [[self.acceptance_run_id], [self.payload_hash], [vector]], timeout=30
            )
            collection.flush(timeout=30)
        finally:
            connections.disconnect("m0")

    def _read_milvus(self) -> str:
        self.connect_milvus()
        try:
            collection = Collection("m0_gate", using="m0")
            collection.load(timeout=30)
            rows = collection.query(
                expr=f'acceptance_run_id == "{self.acceptance_run_id}"',
                output_fields=["payload_hash"],
                timeout=30,
            )
        finally:
            connections.disconnect("m0")
        if len(rows) != 1:
            raise RuntimeError(f"Milvus expected one readback, got {len(rows)}")
        return str(rows[0]["payload_hash"])

    def _write_neo4j(self) -> None:
        with self.neo4j() as driver:
            driver.execute_query(
                "MERGE (run:M0Gate {acceptance_run_id: $run_id}) "
                "SET run.payload_hash = $payload_hash "
                "MERGE (service:M0Service {name: 'neo4j'}) "
                "MERGE (run)-[:VERIFIED_ON]->(service)",
                run_id=self.acceptance_run_id,
                payload_hash=self.payload_hash,
                database_="neo4j",
            )

    def _read_neo4j(self) -> str:
        with self.neo4j() as driver:
            records, _, _ = driver.execute_query(
                "MATCH (run:M0Gate {acceptance_run_id: $run_id})"
                "-[:VERIFIED_ON]->(:M0Service) "
                "RETURN run.payload_hash AS payload_hash",
                run_id=self.acceptance_run_id,
                database_="neo4j",
            )
        if len(records) != 1:
            raise RuntimeError(f"Neo4j expected one readback, got {len(records)}")
        return str(records[0]["payload_hash"])

    def _keycloak_admin_token(self) -> str:
        response = self.http.post(
            "http://127.0.0.1:18080/realms/master/protocol/openid-connect/token",
            data={
                "grant_type": "password",
                "client_id": "admin-cli",
                "username": self.settings["KEYCLOAK_ADMIN"],
                "password": self.settings["KEYCLOAK_ADMIN_PASSWORD"],
            },
            timeout=10,
        )
        response.raise_for_status()
        return str(response.json()["access_token"])

    def _write_keycloak(self) -> None:
        base = "http://127.0.0.1:18080"
        realm = self.settings["KEYCLOAK_M0_REALM"]
        headers = {"Authorization": f"Bearer {self._keycloak_admin_token()}"}
        realm_response = self.http.get(
            f"{base}/admin/realms/{realm}", headers=headers, timeout=10
        )
        if realm_response.status_code == 404:
            response = self.http.post(
                f"{base}/admin/realms",
                headers=headers,
                json={"realm": realm, "enabled": True},
                timeout=10,
            )
            response.raise_for_status()
        elif realm_response.is_error:
            realm_response.raise_for_status()

        client_id = self.settings["KEYCLOAK_M0_CLIENT_ID"]
        clients = self.http.get(
            f"{base}/admin/realms/{realm}/clients",
            headers=headers,
            params={"clientId": client_id},
            timeout=10,
        )
        clients.raise_for_status()
        representation = {
            "clientId": client_id,
            "enabled": True,
            "publicClient": False,
            "serviceAccountsEnabled": True,
            "standardFlowEnabled": False,
            "secret": self.settings["KEYCLOAK_M0_CLIENT_SECRET"],
        }
        existing = clients.json()
        if existing:
            response = self.http.put(
                f"{base}/admin/realms/{realm}/clients/{existing[0]['id']}",
                headers=headers,
                json={**existing[0], **representation},
                timeout=10,
            )
        else:
            response = self.http.post(
                f"{base}/admin/realms/{realm}/clients",
                headers=headers,
                json=representation,
                timeout=10,
            )
        response.raise_for_status()
        response = self.http.post(
            f"{base}/admin/realms/{realm}/groups",
            headers=headers,
            json={
                "name": self.acceptance_run_id,
                "attributes": {"payload_hash": [self.payload_hash]},
            },
            timeout=10,
        )
        response.raise_for_status()

    def _read_keycloak(self) -> str:
        base = "http://127.0.0.1:18080"
        realm = self.settings["KEYCLOAK_M0_REALM"]
        token_response = self.http.post(
            f"{base}/realms/{realm}/protocol/openid-connect/token",
            data={
                "grant_type": "client_credentials",
                "client_id": self.settings["KEYCLOAK_M0_CLIENT_ID"],
                "client_secret": self.settings["KEYCLOAK_M0_CLIENT_SECRET"],
            },
            timeout=10,
        )
        token_response.raise_for_status()
        if not token_response.json().get("access_token"):
            raise RuntimeError("Keycloak did not issue a token")
        headers = {"Authorization": f"Bearer {self._keycloak_admin_token()}"}
        groups = self.http.get(
            f"{base}/admin/realms/{realm}/groups",
            headers=headers,
            params={"search": self.acceptance_run_id, "exact": "true"},
            timeout=10,
        )
        groups.raise_for_status()
        matches = [group for group in groups.json() if group.get("name") == self.acceptance_run_id]
        if len(matches) != 1:
            raise RuntimeError(f"Keycloak expected one group, got {len(matches)}")
        group = self.http.get(
            f"{base}/admin/realms/{realm}/groups/{matches[0]['id']}",
            headers=headers,
            timeout=10,
        )
        group.raise_for_status()
        return str(group.json()["attributes"]["payload_hash"][0])

    def _ensure_toxiproxy(self) -> None:
        base = "http://127.0.0.1:18474"
        self.http.delete(f"{base}/proxies/m0-redis", timeout=5)
        response = self.http.post(
            f"{base}/proxies",
            json={
                "name": "m0-redis",
                "listen": "0.0.0.0:26379",
                "upstream": "redis:6379",
                "enabled": True,
            },
            timeout=5,
        )
        response.raise_for_status()

    def _write_toxiproxy(self) -> None:
        self._ensure_toxiproxy()
        self.redis(port=26379).set(f"m0:toxiproxy:{self.acceptance_run_id}", self.payload_hash)

    def _read_toxiproxy(self) -> str:
        self._ensure_toxiproxy()
        value = cast(
            str | None,
            self.redis(port=26379).get(f"m0:toxiproxy:{self.acceptance_run_id}"),
        )
        if value is None:
            raise RuntimeError("Toxiproxy-proxied persistent value missing")
        return value


def junit_counts(paths: list[Path]) -> dict[str, int]:
    counts = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    for path in paths:
        root = ET.parse(path).getroot()
        suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
        for suite in suites:
            for key in counts:
                counts[key] += int(suite.attrib.get(key, 0))
    return counts


def validate_gate_counts(counts: dict[str, int]) -> None:
    if counts["tests"] <= 0:
        raise RuntimeError("M0 gate collected no tests")
    if counts["failures"] or counts["errors"] or counts["skipped"]:
        raise RuntimeError(
            "M0 gate requires zero failures, errors, and skips; "
            f"got failures={counts['failures']}, errors={counts['errors']}, "
            f"skipped={counts['skipped']}"
        )


def service_versions(environment: dict[str, str]) -> list[dict[str, str]]:
    container_ids = compose(["ps", "-q"], environment, capture=True).splitlines()
    versions: list[dict[str, str]] = []
    for container_id in container_ids:
        result = command(
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
        versions.append(
            {"container": name.lstrip("/"), "configured": configured, "image_id": image_id}
        )
    return sorted(versions, key=lambda item: item["container"])


def run_gate() -> Path:
    command(["uv", "run", "python", "-m", "scripts.prepare_m0_env"])
    settings = load_env_file(ENV_FILE)
    environment = {**os.environ, **load_env_file(VERSIONS_FILE), **settings}
    environment["DEPLOYMENT_PROFILE"] = "full"
    validate_profile("full", environment)
    verify()

    acceptance_run_id = uuid7()
    artifact_dir = ROOT / "artifacts/gates/M0" / acceptance_run_id
    artifact_dir.mkdir(parents=True)
    started_at = datetime.now(UTC)
    unit_junit = artifact_dir / "unit-junit.xml"
    contract_junit = artifact_dir / "contract-junit.xml"
    commands = [
        "make gate-m0",
        "make verify-design",
        "make lint",
        "make typecheck",
        f"uv run pytest tests/unit --junitxml={unit_junit.relative_to(ROOT)}",
        f"uv run pytest tests/contract --junitxml={contract_junit.relative_to(ROOT)}",
        (
            "docker compose --env-file deploy/versions.env --env-file .env.m0 "
            "--profile full config --quiet"
        ),
        (
            "docker compose --env-file deploy/versions.env --env-file .env.m0 "
            "--profile full up -d --wait --wait-timeout 600"
        ),
        "in-process M0Probe.readiness using authenticated production protocols",
        "in-process M0Probe.write including RabbitMQ publisher confirm",
        *[
            (
                "docker compose --env-file deploy/versions.env --env-file .env.m0 "
                f"--profile full restart {service}"
            )
            for service in PERSISTENCE_SERVICES
        ],
        "after each restart: protocol readiness and authoritative persistent readback",
        "generate profile-specific Milvus configs for staging and production",
        (
            "docker compose --env-file deploy/versions.env --env-file .env.m0 "
            "--profile staging up -d --wait --wait-timeout 600; authenticated readiness"
        ),
        (
            "docker compose --env-file deploy/versions.env --env-file .env.m0 "
            "--profile production up -d --wait --wait-timeout 600; authenticated readiness"
        ),
    ]

    command(["make", "verify-design"])
    command(["make", "lint"])
    command(["make", "typecheck"])
    command(["uv", "run", "pytest", "tests/unit", f"--junitxml={unit_junit}"])
    command(["uv", "run", "pytest", "tests/contract", f"--junitxml={contract_junit}"])
    counts = junit_counts([unit_junit, contract_junit])
    validate_gate_counts(counts)
    compose(["config", "--quiet"], environment)
    compose(["up", "-d", "--wait", "--wait-timeout", "600"], environment)

    probe = M0Probe(settings, acceptance_run_id)
    probe.readiness(environment)
    probe.write()
    readbacks: dict[str, str] = {}
    for service in PERSISTENCE_SERVICES:
        compose(["restart", service], environment)
        probe.readiness(environment, (service,))
        readbacks.update(probe.readback((service,)))
    for profile in ("staging", "production"):
        write_config(profile, settings["MILVUS_ROOT_PASSWORD"])
        profile_environment = {
            **environment,
            "DEPLOYMENT_PROFILE": profile,
            "MILVUS_CONFIG_PATH": f"./.runtime/milvus-{profile}.yaml",
        }
        validate_profile(profile, profile_environment)
        compose(
            ["up", "-d", "--wait", "--wait-timeout", "600"],
            profile_environment,
            profile=profile,
        )
        probe.readiness(profile_environment)
    verify()

    versions = service_versions(environment)
    finished_at = datetime.now(UTC)
    gate = {
        "module": "M0",
        "acceptance_run_id": acceptance_run_id,
        "commit_sha": command(["git", "rev-parse", "HEAD"], capture=True).stdout.strip(),
        "environment": {
            "deployment_profiles": ["full", "staging", "production"],
            "platform": command(
                ["docker", "version", "--format", "{{.Server.Os}}/{{.Server.Arch}}"],
                capture=True,
            ).stdout.strip(),
            "python": command([".venv/bin/python", "--version"], capture=True).stdout.strip(),
        },
        "test_commands": commands,
        "test_count": counts["tests"],
        "failure_count": counts["failures"] + counts["errors"],
        "skip_count": counts["skipped"],
        "service_digests": {item["container"]: item["configured"] for item in versions},
        "real_services_contacted": list(COMPOSE_SERVICES),
        "readback_hashes": readbacks,
        "result": "PASSED",
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
    }
    (artifact_dir / "gate.json").write_text(
        json.dumps(gate, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (artifact_dir / "service_versions.json").write_text(
        json.dumps(versions, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (artifact_dir / "readback_hashes.json").write_text(
        json.dumps(readbacks, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (artifact_dir / "chaos_report.json").write_text(
        json.dumps(
            {
                "fault": (
                    "restart each M0 infrastructure container sequentially without "
                    "deleting volumes"
                ),
                "services": list(PERSISTENCE_SERVICES),
                "persistent_readback": "passed",
                "toxiproxy_note": (
                    "Redis write/read traversed Toxiproxy before and after its restart"
                ),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"OK: M0 gate passed with acceptance_run_id={acceptance_run_id}")
    print(f"OK: sanitized evidence written to {artifact_dir.relative_to(ROOT)}")
    return artifact_dir


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("readiness", "gate"))
    arguments = parser.parse_args()
    command(["uv", "run", "python", "-m", "scripts.prepare_m0_env"])
    settings = load_env_file(ENV_FILE)
    environment = {**os.environ, **load_env_file(VERSIONS_FILE), **settings}
    environment["DEPLOYMENT_PROFILE"] = "full"
    if arguments.action == "gate":
        run_gate()
        return 0
    validate_profile("full", environment)
    M0Probe(settings, uuid7()).readiness(environment)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
