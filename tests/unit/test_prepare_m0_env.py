from pathlib import Path

import pytest

from scripts.prepare_m0_env import main, token
from scripts.prepare_milvus_config import write_config


def test_generated_secret_has_cli_safe_prefix() -> None:
    generated = token()

    assert generated.startswith("m0_")
    assert len(generated) >= 32


def test_milvus_config_is_profile_specific(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("scripts.prepare_milvus_config.RUNTIME_DIR", tmp_path)

    password = "profile: secure # password"
    staging = write_config("staging", password)

    assert staging == tmp_path / "milvus-staging.yaml"
    assert staging.stat().st_mode & 0o777 == 0o600
    assert 'defaultRootPassword: "profile: secure # password"' in staging.read_text(
        encoding="utf-8"
    )


def test_existing_m0_environment_is_restricted_to_owner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    environment = tmp_path / ".env.m0"
    environment.write_text("MILVUS_ROOT_PASSWORD=secure-password\n", encoding="utf-8")
    environment.chmod(0o644)
    monkeypatch.setattr("scripts.prepare_m0_env.ENV_PATH", environment)
    monkeypatch.setattr("scripts.prepare_m0_env.write_milvus_config", lambda _: None)

    assert main() == 0
    assert environment.stat().st_mode & 0o777 == 0o600


def test_new_m0_environment_uses_an_isolated_compose_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    environment = tmp_path / ".env.m0"
    monkeypatch.setattr("scripts.prepare_m0_env.ENV_PATH", environment)
    monkeypatch.setattr("scripts.prepare_m0_env.write_milvus_config", lambda _: None)

    assert main() == 0
    values = environment.read_text(encoding="utf-8")
    assert "COMPOSE_PROJECT_NAME=energy-agent-m0-" in values
    assert "COMPOSE_PROJECT_NAME=energy-agent-m0\n" not in values
