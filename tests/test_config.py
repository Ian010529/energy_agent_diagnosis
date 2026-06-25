"""验证分组配置、环境变量覆盖和敏感值隐藏。"""

import pytest
from pydantic import ValidationError

from energy_agent_diagnosis.core.config import DependencyEndpoint, LoggingSettings, Settings


def test_nested_environment_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EDA_APP__PORT", "8123")
    monkeypatch.setenv("EDA_PROVIDERS__ALARM", "real")

    settings = Settings(_env_file=None)

    assert settings.app.port == 8123
    assert settings.providers.alarm == "real"


def test_secret_is_hidden_from_repr() -> None:
    settings = Settings.model_validate(
        {"auth": {"api_keys": [{"key": "sensitive-value", "user_id": "u1", "roles": ["operator"]}]}}
    )

    assert "sensitive-value" not in repr(settings)


@pytest.mark.parametrize(
    ("protocol", "values"),
    [
        ("http", {"url": None}),
        ("tcp", {"port": None}),
        ("redis", {"port": None}),
    ],
)
def test_enabled_dependency_requires_target(protocol: str, values: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        DependencyEndpoint(enabled=True, protocol=protocol, **values)


def test_invalid_port_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings.model_validate({"app": {"port": 70000}})


def test_non_development_environments_always_use_json_logs() -> None:
    logging = LoggingSettings(json_output=False)

    assert logging.uses_json("test") is True
    assert logging.uses_json("production") is True
    assert logging.uses_json("development") is False


def test_metrics_path_rejects_non_path_values() -> None:
    with pytest.raises(ValidationError):
        Settings.model_validate({"metrics": {"path": "not-a-path"}})
