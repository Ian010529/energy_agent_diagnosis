#!/usr/bin/env python3
"""Create ignored local M0 credentials without printing their values."""

from __future__ import annotations

import secrets
from pathlib import Path

from scripts.prepare_milvus_config import write_config

ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env.m0"


def token(length: int = 32) -> str:
    return "m0_" + secrets.token_urlsafe(length)


def load_existing() -> dict[str, str]:
    values: dict[str, str] = {}
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key] = value
    return values


def write_milvus_config(password: str) -> None:
    write_config("full", password)


def main() -> int:
    if ENV_PATH.exists():
        values = load_existing()
        password = values.get("MILVUS_ROOT_PASSWORD")
        if not password:
            print("FAIL: existing .env.m0 lacks MILVUS_ROOT_PASSWORD")
            return 1
        write_milvus_config(password)
        print("OK: existing ignored .env.m0 retained")
        return 0

    values = {
        "COMPOSE_PROJECT_NAME": "energy-agent-m0",
        "DEPLOYMENT_PROFILE": "full",
        "MYSQL_ROOT_PASSWORD": token(),
        "MYSQL_DATABASE": "energy_agent",
        "MYSQL_USER": "energy_agent",
        "MYSQL_PASSWORD": token(),
        "REDIS_PASSWORD": token(),
        "RABBITMQ_DEFAULT_USER": "energy_agent",
        "RABBITMQ_DEFAULT_PASS": token(),
        "MINIO_ROOT_USER": "energyagent",
        "MINIO_ROOT_PASSWORD": token(),
        "INFLUXDB_USERNAME": "energy_agent",
        "INFLUXDB_PASSWORD": token(),
        "INFLUXDB_ORG": "energy-agent",
        "INFLUXDB_BUCKET": "diagnosis",
        "INFLUXDB_TOKEN": token(48),
        "OPENSEARCH_INITIAL_ADMIN_PASSWORD": "M0a!" + token(),
        "NEO4J_USERNAME": "neo4j",
        "NEO4J_PASSWORD": "M0a!" + token(),
        "KEYCLOAK_ADMIN": "m0-admin",
        "KEYCLOAK_ADMIN_PASSWORD": "M0a!" + token(),
        "KEYCLOAK_M0_REALM": "m0-gate",
        "KEYCLOAK_M0_CLIENT_ID": "m0-gate-client",
        "KEYCLOAK_M0_CLIENT_SECRET": token(),
        "KEYCLOAK_M0_USERNAME": "m0-probe",
        "KEYCLOAK_M0_USER_PASSWORD": "M0a!" + token(),
        "MILVUS_ROOT_PASSWORD": "M0a!" + token(),
    }
    ENV_PATH.write_text(
        "".join(f"{key}={value}\n" for key, value in values.items()), encoding="utf-8"
    )
    ENV_PATH.chmod(0o600)
    write_milvus_config(values["MILVUS_ROOT_PASSWORD"])
    print("OK: generated ignored M0 environment and runtime config")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
