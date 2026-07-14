from pathlib import Path

import pytest

from scripts.prepare_m0_env import token
from scripts.prepare_milvus_config import write_config


def test_generated_secret_has_cli_safe_prefix() -> None:
    generated = token()

    assert generated.startswith("m0_")
    assert len(generated) >= 32


def test_milvus_config_is_profile_specific(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("scripts.prepare_milvus_config.RUNTIME_DIR", tmp_path)

    staging = write_config("staging", "profile-secure-password")

    assert staging == tmp_path / "milvus-staging.yaml"
    assert staging.stat().st_mode & 0o777 == 0o600
    assert "profile-secure-password" in staging.read_text(encoding="utf-8")
