import asyncio
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, or_, select

from energy_agent.app import create_app
from energy_agent.core.config import Settings
from energy_agent.core.context import ActorContext, ActorRole
from energy_agent.core.errors import (
    AuthRefreshReusedError,
    AuthTokenInvalidError,
    UserLastAdminProtectedError,
)
from energy_agent.core.ids import new_id
from energy_agent.core.time import utc_now
from energy_agent.observability.tracing import LocalTracer
from energy_agent.persistence.models import (
    AppUserModel,
    AuditEventModel,
    AuthRefreshSessionModel,
)
from energy_agent.persistence.mysql import create_mysql_engine, create_session_factory
from energy_agent.persistence.repositories.audit import AuditRepository
from energy_agent.users.contracts import UserCreateRequest, UserPatchRequest
from energy_agent.users.jwt import JWTCodec
from energy_agent.users.password import hash_password, normalize_username
from energy_agent.users.repository import RefreshSessionRepository, UserRepository
from energy_agent.users.service import AuthService, UserService

pytestmark = pytest.mark.integration


class NoopRateLimiter:
    async def allow(
        self, actor_id: str, group: str, limit: int, window_seconds: int = 60
    ) -> tuple[bool, int]:
        return True, window_seconds

    async def acquire_stream(self, actor_id: str, limit: int) -> bool:
        return True

    async def release_stream(self, actor_id: str) -> None:
        return None


@pytest.mark.asyncio
async def test_concurrent_admin_removals_preserve_one_active_admin() -> None:
    settings = Settings()
    engine = create_mysql_engine(settings.mysql_dsn)
    factory = create_session_factory(engine)
    tracer = LocalTracer("none")
    users = UserRepository(factory)
    service = UserService(
        users,
        RefreshSessionRepository(factory),
        AuditRepository(factory, tracer),
    )
    suffix = uuid4().hex[:10]
    now = utc_now()
    admin_ids = [new_id(), new_id()]
    try:
        if await users.active_admin_count():
            pytest.skip("requires an isolated auth integration database")
        for index, admin_id in enumerate(admin_ids):
            await users.create(
                {
                    "user_id": admin_id,
                    "username": f"race-admin-{index}-{suffix}",
                    "username_normalized": f"race-admin-{index}-{suffix}",
                    "display_name": f"Race Admin {index}",
                    "email": None,
                    "role": ActorRole.ADMIN.value,
                    "status": "ACTIVE",
                    "password_hash": hash_password(
                        "race-admin-password-1", f"race-admin-{index}-{suffix}"
                    ),
                    "must_change_password": False,
                    "token_version": 1,
                    "failed_login_count": 0,
                    "created_by": None,
                    "created_at": now,
                    "updated_at": now,
                }
            )
        outcomes = await asyncio.gather(
            service.patch(
                admin_ids[1],
                UserPatchRequest(role=ActorRole.OPERATOR),
                ActorContext(admin_ids[0], ActorRole.ADMIN, "jwt"),
                new_id(),
            ),
            service.disable(
                admin_ids[0],
                ActorContext(admin_ids[1], ActorRole.ADMIN, "jwt"),
                new_id(),
            ),
            return_exceptions=True,
        )

        assert sum(isinstance(item, UserLastAdminProtectedError) for item in outcomes) == 1
        assert await users.active_admin_count() == 1
    finally:
        await engine.dispose()
        await tracer.shutdown()
        await _cleanup_suffix(settings, suffix)


async def _seed_admin(settings: Settings, suffix: str) -> tuple[str, str]:
    engine = create_mysql_engine(settings.mysql_dsn)
    factory = create_session_factory(engine)
    admin_id = new_id()
    username = f"api-admin-{suffix}"
    now = utc_now()
    try:
        await UserRepository(factory).create(
            {
                "user_id": admin_id,
                "username": username,
                "username_normalized": normalize_username(username),
                "display_name": "API Admin",
                "email": None,
                "role": "admin",
                "status": "ACTIVE",
                "password_hash": hash_password("admin-password-1", username),
                "must_change_password": False,
                "token_version": 1,
                "failed_login_count": 0,
                "created_by": None,
                "created_at": now,
                "updated_at": now,
            }
        )
        return admin_id, username
    finally:
        await engine.dispose()


async def _cleanup_suffix(settings: Settings, suffix: str) -> None:
    engine = create_mysql_engine(settings.mysql_dsn)
    factory = create_session_factory(engine)
    try:
        async with factory.begin() as session:
            target_ids = list(
                (
                    await session.scalars(
                        AppUserModel.__table__.select()
                        .with_only_columns(AppUserModel.user_id)
                        .where(AppUserModel.username.like(f"%{suffix}"))
                    )
                ).all()
            )
            if target_ids:
                await session.execute(
                    delete(AuthRefreshSessionModel).where(
                        AuthRefreshSessionModel.user_id.in_(target_ids)
                    )
                )
                await session.execute(
                    delete(AuditEventModel).where(
                        or_(
                            AuditEventModel.resource_id.in_(target_ids),
                            AuditEventModel.actor_id.in_(target_ids),
                        )
                    )
                )
                await session.execute(
                    delete(AppUserModel).where(AppUserModel.user_id.in_(target_ids))
                )
    finally:
        await engine.dispose()


def test_jwt_http_contract_forced_change_rbac_and_disable() -> None:
    settings = Settings()
    suffix = uuid4().hex[:10]
    _, username = __import__("asyncio").run(_seed_admin(settings, suffix))
    internal = {
        "X-Internal-API-Key": settings.internal_api_key or "",
        "X-Forwarded-For": f"integration-{suffix}",
    }
    try:
        with TestClient(create_app(settings)) as client:
            admin_login = client.post(
                "/api/v1/auth/login",
                headers=internal,
                json={"username": username, "password": "admin-password-1"},
            )
            assert admin_login.status_code == 200
            admin_access = admin_login.json()["access_token"]
            admin_headers = {**internal, "Authorization": f"Bearer {admin_access}"}
            created = client.post(
                "/api/v1/users",
                headers=admin_headers,
                json={
                    "username": f"api-operator-{suffix}",
                    "display_name": "API Operator",
                    "email": f"operator-{suffix}@example.test",
                    "role": "operator",
                    "initial_password": "operator-password-1",
                },
            )
            assert created.status_code == 201
            operator_id = created.json()["user_id"]
            duplicate_username = client.post(
                "/api/v1/users",
                headers=admin_headers,
                json={
                    "username": f"api-operator-{suffix}",
                    "display_name": "Duplicate Username",
                    "role": "viewer",
                    "initial_password": "duplicate-password-1",
                },
            )
            assert duplicate_username.status_code == 409
            assert duplicate_username.json()["error"]["code"] == "USER_USERNAME_EXISTS"
            duplicate_email = client.post(
                "/api/v1/users",
                headers=admin_headers,
                json={
                    "username": f"api-email-duplicate-{suffix}",
                    "display_name": "Duplicate Email",
                    "email": f"operator-{suffix}@example.test",
                    "role": "viewer",
                    "initial_password": "duplicate-password-1",
                },
            )
            assert duplicate_email.status_code == 409
            assert duplicate_email.json()["error"]["code"] == "USER_EMAIL_EXISTS"
            locked_user = client.post(
                "/api/v1/users",
                headers=admin_headers,
                json={
                    "username": f"api-locked-{suffix}",
                    "display_name": "API Locked",
                    "role": "viewer",
                    "initial_password": "locked-password-1",
                },
            )
            assert locked_user.status_code == 201
            for attempt in range(5):
                failed = client.post(
                    "/api/v1/auth/login",
                    headers=internal,
                    json={
                        "username": f"api-locked-{suffix}",
                        "password": "wrong-password",
                    },
                )
                assert failed.status_code == 401
                assert failed.json()["error"]["code"] == (
                    "AUTH_ACCOUNT_LOCKED" if attempt == 4 else "AUTH_INVALID_CREDENTIALS"
                )
            operator_login = client.post(
                "/api/v1/auth/login",
                headers=internal,
                json={
                    "username": f"api-operator-{suffix}",
                    "password": "operator-password-1",
                },
            )
            assert operator_login.status_code == 200
            operator_headers = {
                **internal,
                "Authorization": f"Bearer {operator_login.json()['access_token']}",
            }
            blocked = client.get("/api/v1/capabilities", headers=operator_headers)
            assert blocked.status_code == 403
            assert blocked.json()["error"]["code"] == "AUTH_PASSWORD_CHANGE_REQUIRED"
            changed = client.post(
                "/api/v1/auth/change-password",
                headers=operator_headers,
                json={
                    "current_password": "operator-password-1",
                    "new_password": "operator-password-2",
                },
            )
            assert changed.status_code == 200
            changed_headers = {
                **internal,
                "Authorization": f"Bearer {changed.json()['access_token']}",
            }
            assert client.get("/api/v1/capabilities", headers=changed_headers).status_code == 200
            assert client.get("/api/v1/users", headers=changed_headers).status_code == 403
            assert (
                client.post(
                    f"/api/v1/users/{operator_id}/disable", headers=admin_headers
                ).status_code
                == 200
            )
            rejected = client.get("/api/v1/auth/me", headers=changed_headers)
            assert rejected.status_code == 401
            assert rejected.json()["error"]["code"] == "AUTH_TOKEN_INVALID"
    finally:
        __import__("asyncio").run(_cleanup_suffix(settings, suffix))


def test_admin_user_lifecycle_token_invalidation_logout_all_and_audit() -> None:
    settings = Settings(
        rate_limit_auth_login_username=20,
        rate_limit_auth_login_source=50,
    )
    suffix = uuid4().hex[:10]
    admin_id, username = __import__("asyncio").run(_seed_admin(settings, suffix))
    internal = {
        "X-Internal-API-Key": settings.internal_api_key or "",
        "X-Forwarded-For": f"lifecycle-{suffix}",
    }
    try:
        with TestClient(create_app(settings)) as client:
            admin_login = client.post(
                "/api/v1/auth/login",
                headers=internal,
                json={"username": username, "password": "admin-password-1"},
            )
            assert admin_login.status_code == 200
            admin_headers = {
                **internal,
                "Authorization": f"Bearer {admin_login.json()['access_token']}",
            }
            self_role = client.patch(
                f"/api/v1/users/{admin_id}",
                headers=admin_headers,
                json={"role": "operator"},
            )
            assert self_role.status_code == 403
            assert self_role.json()["error"]["code"] == "USER_SELF_ROLE_CHANGE_FORBIDDEN"
            self_disable = client.post(
                f"/api/v1/users/{admin_id}/disable",
                headers=admin_headers,
            )
            assert self_disable.status_code == 403
            assert self_disable.json()["error"]["code"] == "USER_SELF_DISABLE_FORBIDDEN"

            created = client.post(
                "/api/v1/users",
                headers=admin_headers,
                json={
                    "username": f"lifecycle-{suffix}",
                    "display_name": "Lifecycle User",
                    "role": "operator",
                    "initial_password": "lifecycle-password-1",
                },
            )
            assert created.status_code == 201
            user_id = created.json()["user_id"]

            first_login = client.post(
                "/api/v1/auth/login",
                headers=internal,
                json={
                    "username": f"lifecycle-{suffix}",
                    "password": "lifecycle-password-1",
                },
            )
            first_headers = {
                **internal,
                "Authorization": f"Bearer {first_login.json()['access_token']}",
            }
            changed = client.post(
                "/api/v1/auth/change-password",
                headers=first_headers,
                json={
                    "current_password": "lifecycle-password-1",
                    "new_password": "lifecycle-password-2",
                },
            )
            assert changed.status_code == 200
            active = changed.json()
            active_headers = {
                **internal,
                "Authorization": f"Bearer {active['access_token']}",
            }

            updated = client.patch(
                f"/api/v1/users/{user_id}",
                headers=admin_headers,
                json={"display_name": "Lifecycle Updated"},
            )
            assert updated.status_code == 200
            role_changed = client.patch(
                f"/api/v1/users/{user_id}",
                headers=admin_headers,
                json={"role": "reviewer"},
            )
            assert role_changed.status_code == 200
            assert role_changed.json()["role"] == "reviewer"
            assert client.get("/api/v1/auth/me", headers=active_headers).status_code == 401
            assert (
                client.post(
                    "/api/v1/auth/refresh",
                    headers=internal,
                    json={"refresh_token": active["refresh_token"]},
                ).status_code
                == 401
            )

            reviewer_login = client.post(
                "/api/v1/auth/login",
                headers=internal,
                json={
                    "username": f"lifecycle-{suffix}",
                    "password": "lifecycle-password-2",
                },
            )
            assert reviewer_login.status_code == 200
            assert reviewer_login.json()["user"]["role"] == "reviewer"
            reviewer_headers = {
                **internal,
                "Authorization": f"Bearer {reviewer_login.json()['access_token']}",
            }
            assert client.get("/api/v1/users", headers=reviewer_headers).status_code == 403

            revoked = client.post(
                f"/api/v1/users/{user_id}/revoke-sessions",
                headers=admin_headers,
            )
            assert revoked.status_code == 200
            assert client.get("/api/v1/auth/me", headers=reviewer_headers).status_code == 401

            reset = client.post(
                f"/api/v1/users/{user_id}/reset-password",
                headers=admin_headers,
                json={"temporary_password": "lifecycle-temporary-3"},
            )
            assert reset.status_code == 200
            assert reset.json()["must_change_password"] is True
            assert (
                client.post(
                    "/api/v1/auth/login",
                    headers=internal,
                    json={
                        "username": f"lifecycle-{suffix}",
                        "password": "lifecycle-password-2",
                    },
                ).status_code
                == 401
            )
            temporary_login = client.post(
                "/api/v1/auth/login",
                headers=internal,
                json={
                    "username": f"lifecycle-{suffix}",
                    "password": "lifecycle-temporary-3",
                },
            )
            assert temporary_login.status_code == 200

            disabled = client.post(
                f"/api/v1/users/{user_id}/disable",
                headers=admin_headers,
            )
            assert disabled.status_code == 200
            assert disabled.json()["status"] == "DISABLED"
            temporary_headers = {
                **internal,
                "Authorization": f"Bearer {temporary_login.json()['access_token']}",
            }
            assert client.get("/api/v1/auth/me", headers=temporary_headers).status_code == 401
            assert (
                client.post(
                    "/api/v1/auth/login",
                    headers=internal,
                    json={
                        "username": f"lifecycle-{suffix}",
                        "password": "lifecycle-temporary-3",
                    },
                ).status_code
                == 401
            )

            enabled = client.post(
                f"/api/v1/users/{user_id}/enable",
                headers=admin_headers,
            )
            assert enabled.status_code == 200
            assert enabled.json()["status"] == "ACTIVE"
            enabled_login = client.post(
                "/api/v1/auth/login",
                headers=internal,
                json={
                    "username": f"lifecycle-{suffix}",
                    "password": "lifecycle-temporary-3",
                },
            )
            assert enabled_login.status_code == 200
            enabled_headers = {
                **internal,
                "Authorization": f"Bearer {enabled_login.json()['access_token']}",
            }
            logout_all = client.post("/api/v1/auth/logout-all", headers=enabled_headers)
            assert logout_all.status_code == 204
            assert client.get("/api/v1/auth/me", headers=enabled_headers).status_code == 401
            assert (
                client.post(
                    "/api/v1/auth/refresh",
                    headers=internal,
                    json={"refresh_token": enabled_login.json()["refresh_token"]},
                ).status_code
                == 401
            )

        engine = create_mysql_engine(settings.mysql_dsn)
        factory = create_session_factory(engine)
        try:

            async def read_actions() -> list[tuple[str, object]]:
                async with factory() as session:
                    return list(
                        (
                            await session.execute(
                                select(
                                    AuditEventModel.action,
                                    AuditEventModel.safe_snapshot,
                                ).where(
                                    or_(
                                        AuditEventModel.resource_id == user_id,
                                        AuditEventModel.actor_id == user_id,
                                    )
                                )
                            )
                        ).all()
                    )

            audits = __import__("asyncio").run(read_actions())
        finally:
            __import__("asyncio").run(engine.dispose())
        actions = {row[0] for row in audits}
        assert {
            "user.created",
            "user.profile_updated",
            "user.role_changed",
            "user.sessions_revoked",
            "user.password_reset",
            "user.disabled",
            "user.enabled",
            "auth.logout_all",
        } <= actions
        serialized = str(audits).lower()
        assert "lifecycle-password" not in serialized
        assert "lifecycle-temporary" not in serialized
        assert "eyj" not in serialized
    finally:
        __import__("asyncio").run(_cleanup_suffix(settings, suffix))


@pytest.mark.asyncio
async def test_admin_create_first_login_change_password_rotation_and_reuse() -> None:
    settings = Settings()
    engine = create_mysql_engine(settings.mysql_dsn)
    factory = create_session_factory(engine)
    tracer = LocalTracer("none")
    users = UserRepository(factory)
    refresh_sessions = RefreshSessionRepository(factory)
    audit = AuditRepository(factory, tracer)
    auth = AuthService(
        users, refresh_sessions, audit, JWTCodec(settings), NoopRateLimiter(), settings
    )
    admin_users = UserService(users, refresh_sessions, audit)
    suffix = uuid4().hex[:10]
    admin_id = new_id()
    now = utc_now()
    try:
        await users.create(
            {
                "user_id": admin_id,
                "username": f"admin-{suffix}",
                "username_normalized": normalize_username(f"admin-{suffix}"),
                "display_name": "Integration Admin",
                "email": None,
                "role": "admin",
                "status": "ACTIVE",
                "password_hash": hash_password("admin-password-1", f"admin-{suffix}"),
                "must_change_password": False,
                "token_version": 1,
                "failed_login_count": 0,
                "created_by": None,
                "created_at": now,
                "updated_at": now,
            }
        )
        admin_actor = ActorContext(admin_id, ActorRole.ADMIN, "jwt")
        operator = await admin_users.create(
            UserCreateRequest(
                username=f"operator-{suffix}",
                display_name="Integration Operator",
                role=ActorRole.OPERATOR,
                initial_password="operator-password-1",
            ),
            admin_actor,
            new_id(),
        )
        first = await auth.login(
            operator.username,
            "operator-password-1",
            trace_id=new_id(),
            ip="127.0.0.1",
            user_agent="pytest",
        )
        assert first.user.must_change_password is True
        actor, _ = await auth.authenticate_access(first.access_token)
        changed = await auth.change_password(
            actor,
            "operator-password-1",
            "operator-password-2",
            trace_id=new_id(),
            ip="127.0.0.1",
            user_agent="pytest",
        )
        assert changed.user.must_change_password is False
        with pytest.raises(AuthTokenInvalidError):
            await auth.authenticate_access(first.access_token)
        rotated = await auth.refresh(
            changed.refresh_token,
            trace_id=new_id(),
            ip="127.0.0.1",
            user_agent="pytest",
        )
        assert rotated.refresh_token != changed.refresh_token
        with pytest.raises(AuthRefreshReusedError):
            await auth.refresh(
                changed.refresh_token,
                trace_id=new_id(),
                ip="127.0.0.1",
                user_agent="pytest",
            )
        with pytest.raises(AuthTokenInvalidError):
            await auth.authenticate_access(rotated.access_token)
        async with factory() as session:
            audits = list(
                (
                    await session.execute(
                        select(AuditEventModel.action, AuditEventModel.safe_snapshot).where(
                            or_(
                                AuditEventModel.resource_id.in_([admin_id, operator.user_id]),
                                AuditEventModel.actor_id == operator.user_id,
                            )
                        )
                    )
                ).all()
            )
        assert {
            "user.created",
            "auth.login.succeeded",
            "auth.password.changed",
            "auth.refresh.succeeded",
            "auth.refresh.reuse_detected",
        } <= {row.action for row in audits}
        serialized_audit = str(audits).lower()
        assert "operator-password" not in serialized_audit
        assert "eyj" not in serialized_audit
    finally:
        async with factory.begin() as session:
            target_ids = list(
                (
                    await session.scalars(
                        AppUserModel.__table__.select()
                        .with_only_columns(AppUserModel.user_id)
                        .where(AppUserModel.username.like(f"%{suffix}"))
                    )
                ).all()
            )
            if target_ids:
                await session.execute(
                    delete(AuthRefreshSessionModel).where(
                        AuthRefreshSessionModel.user_id.in_(target_ids)
                    )
                )
                await session.execute(
                    delete(AuditEventModel).where(
                        or_(
                            AuditEventModel.resource_id.in_(target_ids),
                            AuditEventModel.actor_id.in_(target_ids),
                        )
                    )
                )
                await session.execute(
                    delete(AppUserModel).where(AppUserModel.user_id.in_(target_ids))
                )
        await tracer.shutdown()
        await engine.dispose()
