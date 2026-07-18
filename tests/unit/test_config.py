import pytest
from pydantic import ValidationError

from energy_agent.core.config import Settings


def test_local_settings_do_not_require_langfuse_credentials() -> None:
    settings = Settings(observability_mode="local")
    assert settings.redis_session_ttl_seconds == 86_400


def test_langfuse_mode_requires_credentials() -> None:
    with pytest.raises(ValidationError, match="LANGFUSE_PUBLIC_KEY"):
        Settings(
            observability_mode="langfuse",
            langfuse_public_key=None,
            langfuse_secret_key=None,
        )


def test_settings_reject_invalid_ttl() -> None:
    with pytest.raises(ValidationError):
        Settings(redis_session_ttl_seconds=0)
