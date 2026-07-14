#!/usr/bin/env python3
"""Fail closed when a protected profile has missing or unsafe configuration."""

from __future__ import annotations

import os
import sys

PROTECTED = {"full", "staging", "production"}
REQUIRED = {
    "MYSQL_ROOT_PASSWORD",
    "MYSQL_DATABASE",
    "MYSQL_USER",
    "MYSQL_PASSWORD",
    "REDIS_PASSWORD",
    "RABBITMQ_DEFAULT_USER",
    "RABBITMQ_DEFAULT_PASS",
    "MINIO_ROOT_USER",
    "MINIO_ROOT_PASSWORD",
    "INFLUXDB_USERNAME",
    "INFLUXDB_PASSWORD",
    "INFLUXDB_ORG",
    "INFLUXDB_BUCKET",
    "INFLUXDB_TOKEN",
    "OPENSEARCH_INITIAL_ADMIN_PASSWORD",
    "NEO4J_USERNAME",
    "NEO4J_PASSWORD",
    "KEYCLOAK_ADMIN",
    "KEYCLOAK_ADMIN_PASSWORD",
    "MILVUS_ROOT_PASSWORD",
}
PLACEHOLDERS = {"change-me", "changeme", "example", "placeholder", "todo"}
SECRET_KEYS = {
    "MYSQL_ROOT_PASSWORD",
    "MYSQL_PASSWORD",
    "REDIS_PASSWORD",
    "RABBITMQ_DEFAULT_PASS",
    "MINIO_ROOT_PASSWORD",
    "INFLUXDB_PASSWORD",
    "INFLUXDB_TOKEN",
    "OPENSEARCH_INITIAL_ADMIN_PASSWORD",
    "NEO4J_PASSWORD",
    "KEYCLOAK_ADMIN_PASSWORD",
    "MILVUS_ROOT_PASSWORD",
}


def validate(profile: str, environment: dict[str, str]) -> None:
    if profile not in {"dev", *PROTECTED}:
        raise RuntimeError(f"unknown deployment profile: {profile}")
    if profile not in PROTECTED:
        return
    invalid = sorted(
        key
        for key in REQUIRED
        if not environment.get(key)
        or environment[key].strip().lower() in PLACEHOLDERS
        or (key in SECRET_KEYS and len(environment[key].strip()) < 8)
    )
    forbidden = sorted(
        key
        for key, value in environment.items()
        if value and any(marker in key.upper() for marker in ("MOCK", "FIXTURE", "GOLD_PATH"))
    )
    if invalid or forbidden:
        raise RuntimeError(
            f"protected profile rejected; invalid={invalid}, forbidden={forbidden}"
        )


def main() -> int:
    profile = sys.argv[1] if len(sys.argv) == 2 else os.getenv("DEPLOYMENT_PROFILE", "")
    try:
        validate(profile, dict(os.environ))
    except RuntimeError as error:
        print(f"FAIL: {error}")
        return 1
    print(f"OK: deployment profile {profile} passed startup protection")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
