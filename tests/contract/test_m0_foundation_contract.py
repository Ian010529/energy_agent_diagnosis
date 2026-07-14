from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest

from scripts.validate_profile import REQUIRED, validate

ROOT = Path(__file__).resolve().parents[2]
EXPECTED_IMAGES = {
    "MYSQL_IMAGE",
    "REDIS_IMAGE",
    "RABBITMQ_IMAGE",
    "MINIO_IMAGE",
    "MINIO_MC_IMAGE",
    "INFLUXDB_IMAGE",
    "OPENSEARCH_IMAGE",
    "MILVUS_IMAGE",
    "ETCD_IMAGE",
    "NEO4J_IMAGE",
    "KEYCLOAK_IMAGE",
    "TOXIPROXY_IMAGE",
}


def parse_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key] = value
    return values


def safe_contract_environment() -> dict[str, str]:
    environment = {**os.environ, **parse_env(ROOT / "deploy/versions.env")}
    environment.update({key: f"contract-{key.lower()}-value" for key in REQUIRED})
    environment.update(
        {
            "COMPOSE_PROJECT_NAME": "energy-agent-contract",
            "DEPLOYMENT_PROFILE": "full",
            "KEYCLOAK_M0_REALM": "contract",
            "KEYCLOAK_M0_CLIENT_ID": "contract",
            "KEYCLOAK_M0_CLIENT_SECRET": "contract-client-secret",
            "KEYCLOAK_M0_USERNAME": "contract",
            "KEYCLOAK_M0_USER_PASSWORD": "contract-user-password",
        }
    )
    return environment


def test_all_infrastructure_images_are_digest_pinned() -> None:
    versions = parse_env(ROOT / "deploy/versions.env")

    assert set(versions) == EXPECTED_IMAGES
    assert all(
        re.fullmatch(r"[^\s]+@sha256:[0-9a-f]{64}", reference)
        for reference in versions.values()
    )
    assert all(":latest" not in reference for reference in versions.values())


def test_compose_exposes_all_frozen_profiles() -> None:
    result = subprocess.run(
        ["docker", "compose", "--profile", "full", "config", "--profiles"],
        cwd=ROOT,
        env=safe_contract_environment(),
        check=True,
        text=True,
        capture_output=True,
    )

    assert set(result.stdout.splitlines()) == {"dev", "full", "staging", "production"}


def test_compose_configuration_is_valid_without_starting_services() -> None:
    subprocess.run(
        ["docker", "compose", "--profile", "full", "config", "--quiet"],
        cwd=ROOT,
        env=safe_contract_environment(),
        check=True,
        text=True,
        capture_output=True,
    )


def test_healthchecks_do_not_put_credentials_in_process_arguments() -> None:
    compose = (ROOT / "compose.yaml").read_text(encoding="utf-8")

    assert "cypher-shell" not in compose
    assert "redis-cli -a" not in compose
    assert "-p$$MYSQL_PASSWORD" not in compose
    assert "curl -fsS -u admin:" not in compose


def test_protected_profile_fails_closed() -> None:
    environment = {key: "contract-secure-value" for key in REQUIRED}
    validate("full", environment)

    with pytest.raises(RuntimeError, match="invalid"):
        validate("production", {**environment, "MYSQL_PASSWORD": "change-me"})
    with pytest.raises(RuntimeError, match="forbidden"):
        validate("staging", {**environment, "RUNTIME_MOCK_PROVIDER": "enabled"})


def test_env_example_contains_names_but_no_values() -> None:
    values = parse_env(ROOT / ".env.example")

    assert set(values) >= REQUIRED
    assert all(value == "" for value in values.values())


def test_m0_status_and_immutable_checksum_are_frozen() -> None:
    status = (ROOT / "docs/IMPLEMENTATION_STATUS.yaml").read_text(encoding="utf-8")
    checksums = (ROOT / "docs/immutable/SHA256SUMS").read_text(encoding="utf-8")

    assert "current_module: M0" in status
    assert "status: IN_PROGRESS" in status
    assert "c559a530387de5fc1afced506e406967e74c18ed76e659b4b062c2051b615a11" in checksums


def test_helm_skeleton_references_an_existing_secret() -> None:
    values = (ROOT / "deploy/helm/energy-agent/values.yaml").read_text(encoding="utf-8")

    assert "existingSecret:" in values
    assert "password:" not in values.lower()
    assert "secret:" not in values.lower().replace("existingsecret:", "")


def test_greenfield_top_level_skeleton_exists() -> None:
    expected = [
        "src/energy_agent/api",
        "src/energy_agent/contracts",
        "src/energy_agent/core",
        "src/energy_agent/auth",
        "src/energy_agent/runtime",
        "src/energy_agent/agent",
        "src/energy_agent/tools",
        "src/energy_agent/providers",
        "src/energy_agent/retrieval",
        "src/energy_agent/memory",
        "src/energy_agent/model",
        "src/energy_agent/persistence",
        "src/energy_agent/observability",
        "src/energy_agent/services",
        "migrations/control",
        "migrations/ops",
        "data_factory/scenarios",
        "data_factory/generator",
        "data_factory/validator",
        "data_factory/loader",
        "data_factory/evaluator_assets",
        "tests/integration",
        "tests/live",
        "tests/chaos",
        "tests/performance",
        "tests/packaging",
        "deploy/keycloak",
        "deploy/dashboards",
        "docs/gates/M0",
        "docs/runbooks",
        "docs/api",
    ]

    assert all((ROOT / path).is_dir() for path in expected)
