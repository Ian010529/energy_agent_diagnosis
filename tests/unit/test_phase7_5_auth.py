from datetime import timedelta
from unittest.mock import AsyncMock

import jwt
import pytest
from sqlalchemy.exc import IntegrityError

from energy_agent.app import _uses_generic_write_rate_limit
from energy_agent.core.config import Settings
from energy_agent.core.context import ActorContext, ActorRole
from energy_agent.core.errors import AuthNewPasswordInvalidError
from energy_agent.core.time import utc_now
from energy_agent.users.contracts import UserCreateRequest, UserProfile, UserStatus
from energy_agent.users.jwt import JWTCodec
from energy_agent.users.password import (
    dummy_verify,
    hash_password,
    normalize_username,
    verify_password,
)
from energy_agent.users.repository import _duplicate_key_is_email, token_digest
from energy_agent.users.service import AuthService, UserService


def jwt_settings() -> Settings:
    return Settings(
        app_env="test",
        auth_mode="jwt",
        internal_api_key="internal",
        jwt_access_secret="a" * 32,
        jwt_refresh_secret="b" * 32,
    )


def test_auth_endpoints_use_only_their_dedicated_rate_limits() -> None:
    assert not _uses_generic_write_rate_limit("POST", "/api/v1/auth/login")
    assert not _uses_generic_write_rate_limit("POST", "/api/v1/auth/refresh")
    assert _uses_generic_write_rate_limit("POST", "/api/v1/auth/change-password")
    assert _uses_generic_write_rate_limit("POST", "/api/v1/diagnosis/sessions")


def test_username_normalization_argon2id_and_dummy_verify() -> None:
    assert normalize_username("  ＯＰＥＲＡＴＯＲ01 ") == "operator01"
    password_hash = hash_password("strong-password", "operator01")
    assert password_hash.startswith("$argon2id$")
    assert verify_password("strong-password", password_hash)
    assert not verify_password("wrong-password", password_hash)
    assert dummy_verify("anything") is None
    with pytest.raises(AuthNewPasswordInvalidError):
        hash_password("operator01", "operator01")


def test_access_and_refresh_jwt_are_separate_and_strict() -> None:
    codec = JWTCodec(jwt_settings())
    access = codec.issue_access(
        user_id="user-1", username="operator01", role="operator", token_version=1
    )
    refresh = codec.issue_refresh(
        user_id="user-1",
        session_id="session-1",
        family_id="family-1",
        jti="refresh-jti",
        token_version=1,
    )
    assert codec.decode_access(access.token)["type"] == "access"
    assert codec.decode_refresh(refresh.token)["type"] == "refresh"
    with pytest.raises(jwt.InvalidTokenError):
        codec.decode_access(refresh.token)
    with pytest.raises(jwt.InvalidTokenError):
        codec.decode_refresh(access.token)


def test_jwt_rejects_wrong_issuer_audience_algorithm_and_expiry() -> None:
    settings = jwt_settings()
    codec = JWTCodec(settings)
    now = utc_now()
    base = {
        "sub": "user-1",
        "jti": "jti",
        "type": "access",
        "token_version": 1,
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_access_audience,
        "iat": now,
        "nbf": now,
        "exp": now + timedelta(minutes=1),
    }
    for mutation in (
        {"iss": "wrong"},
        {"aud": "wrong"},
        {"exp": now - timedelta(seconds=1)},
    ):
        token = jwt.encode({**base, **mutation}, settings.jwt_access_secret, algorithm="HS256")
        with pytest.raises(jwt.InvalidTokenError):
            codec.decode_access(token)
    token = jwt.encode(base, "not-the-secret" * 4, algorithm="HS384")
    with pytest.raises(jwt.InvalidTokenError):
        codec.decode_access(token)


def test_single_role_contract_and_refresh_digest() -> None:
    payload = UserCreateRequest(
        username="operator01",
        display_name="Operator",
        role=ActorRole.OPERATOR,
        initial_password="strong-password",
    )
    assert payload.role == ActorRole.OPERATOR
    assert "roles" not in payload.model_dump()
    assert token_digest("refresh-token") != "refresh-token"


def test_jwt_configuration_requires_distinct_long_secrets() -> None:
    with pytest.raises(ValueError):
        Settings(
            app_env="test",
            auth_mode="jwt",
            internal_api_key="internal",
            jwt_access_secret="same" * 8,
            jwt_refresh_secret="same" * 8,
        )


def test_duplicate_key_classification_uses_constraint_name_not_insert_columns() -> None:
    username_error = IntegrityError(
        "INSERT INTO app_user (username_normalized, email) VALUES (%s, %s)",
        ("duplicate", None),
        Exception("Duplicate entry 'duplicate' for key 'app_user.username_normalized'"),
    )
    email_error = IntegrityError(
        "INSERT INTO app_user (username_normalized, email) VALUES (%s, %s)",
        ("unique", "duplicate@example.test"),
        Exception("Duplicate entry 'duplicate@example.test' for key 'app_user.email'"),
    )
    assert not _duplicate_key_is_email(username_error)
    assert _duplicate_key_is_email(email_error)


@pytest.mark.asyncio
async def test_create_user_normalizes_blank_optional_email_to_null() -> None:
    now = utc_now()
    users = AsyncMock()
    users.create.return_value = UserProfile(
        user_id="user-1",
        username="operator01",
        display_name="Operator",
        email=None,
        role=ActorRole.OPERATOR,
        status=UserStatus.ACTIVE,
        must_change_password=True,
        created_at=now,
        updated_at=now,
    )
    audit = AsyncMock()
    service = UserService(users, AsyncMock(), audit)

    await service.create(
        UserCreateRequest(
            username="operator01",
            display_name="Operator",
            email="   ",
            role=ActorRole.OPERATOR,
            initial_password="strong-password",
        ),
        ActorContext("admin-1", ActorRole.ADMIN, "jwt"),
        "trace-1",
    )

    assert users.create.await_args.args[0]["email"] is None


@pytest.mark.asyncio
async def test_logout_audits_even_when_the_refresh_token_is_invalid() -> None:
    audit = AsyncMock()
    service = AuthService(
        AsyncMock(),
        AsyncMock(),
        audit,
        JWTCodec(jwt_settings()),
        AsyncMock(),
        jwt_settings(),
    )
    actor = ActorContext("user-1", ActorRole.OPERATOR, "jwt")

    await service.logout(actor, "invalid-refresh-token", "trace-1")

    audit.write.assert_awaited_once_with(
        actor=actor,
        action="auth.logout",
        resource_type="user",
        resource_id="user-1",
        trace_id="trace-1",
    )
