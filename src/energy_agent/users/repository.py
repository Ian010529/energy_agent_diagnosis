import re
from datetime import timedelta
from typing import Any, cast

from sqlalchemy import func, or_, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from energy_agent.core.context import ActorRole
from energy_agent.core.errors import (
    UserEmailExistsError,
    UserLastAdminProtectedError,
    UserUsernameExistsError,
)
from energy_agent.core.time import ensure_utc, utc_now
from energy_agent.persistence.models import AppUserModel, AuthRefreshSessionModel
from energy_agent.users.contracts import UserProfile, UserStatus
from energy_agent.users.tokens import token_digest

__all__ = [
    "RefreshSessionRepository",
    "UserRepository",
    "_duplicate_key_is_email",
    "token_digest",
]


def _duplicate_key_is_email(exc: IntegrityError) -> bool:
    message = str(getattr(exc, "orig", exc)).lower()
    mysql_key = re.search(r"for key ['`\"]([^'`\"]+)['`\"]", message)
    if mysql_key:
        return mysql_key.group(1).split(".")[-1] == "email"
    return "unique constraint failed: app_user.email" in message


def _profile(model: AppUserModel) -> UserProfile:
    return UserProfile(
        user_id=model.user_id,
        username=model.username,
        display_name=model.display_name,
        email=model.email,
        role=ActorRole(model.role),
        status=UserStatus(model.status),
        must_change_password=model.must_change_password,
        last_login_at=model.last_login_at,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


class UserRepository:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self.sessions = sessions

    async def by_normalized_username(self, username: str) -> AppUserModel | None:
        async with self.sessions() as session:
            return cast(
                AppUserModel | None,
                await session.scalar(
                    select(AppUserModel).where(AppUserModel.username_normalized == username)
                ),
            )

    async def by_id(self, user_id: str) -> AppUserModel | None:
        async with self.sessions() as session:
            return await session.get(AppUserModel, user_id)

    async def profile(self, user_id: str) -> UserProfile | None:
        model = await self.by_id(user_id)
        return _profile(model) if model else None

    async def create(self, values: dict[str, object]) -> UserProfile:
        model = AppUserModel(**values)
        try:
            async with self.sessions.begin() as session:
                session.add(model)
        except IntegrityError as exc:
            if _duplicate_key_is_email(exc):
                raise UserEmailExistsError("Email already exists") from exc
            raise UserUsernameExistsError("Username already exists") from exc
        return _profile(model)

    async def list(
        self,
        *,
        q: str | None,
        role: ActorRole | None,
        status: UserStatus | None,
        limit: int,
        cursor: str | None,
    ) -> tuple[list[UserProfile], bool]:
        statement = select(AppUserModel)
        if q:
            term = f"%{q}%"
            statement = statement.where(
                or_(
                    AppUserModel.username_normalized.like(term),
                    AppUserModel.display_name.like(term),
                    AppUserModel.email.like(term),
                )
            )
        if role:
            statement = statement.where(AppUserModel.role == role.value)
        if status:
            statement = statement.where(AppUserModel.status == status.value)
        if cursor:
            statement = statement.where(AppUserModel.user_id > cursor)
        async with self.sessions() as session:
            models = list(
                (
                    await session.scalars(statement.order_by(AppUserModel.user_id).limit(limit + 1))
                ).all()
            )
        return [_profile(item) for item in models[:limit]], len(models) > limit

    async def update_profile(
        self,
        user_id: str,
        *,
        display_name: str | None,
        email: str | None,
        email_set: bool,
        role: ActorRole | None,
    ) -> tuple[UserProfile | None, ActorRole | None]:
        try:
            async with self.sessions.begin() as session:
                active_admin_ids: list[str] | None = None
                if role is not None and role != ActorRole.ADMIN:
                    active_admin_ids = list(
                        (
                            await session.scalars(
                                select(AppUserModel.user_id)
                                .where(
                                    AppUserModel.role == ActorRole.ADMIN.value,
                                    AppUserModel.status == UserStatus.ACTIVE.value,
                                )
                                .with_for_update()
                            )
                        ).all()
                    )
                model = await session.get(AppUserModel, user_id, with_for_update=True)
                if not model:
                    return None, None
                old_role = ActorRole(model.role)
                if (
                    active_admin_ids is not None
                    and old_role == ActorRole.ADMIN
                    and model.status == UserStatus.ACTIVE.value
                    and len(active_admin_ids) <= 1
                ):
                    raise UserLastAdminProtectedError("Last active admin is protected")
                if display_name is not None:
                    model.display_name = display_name
                if email_set:
                    model.email = email or None
                if role is not None:
                    model.role = role.value
                    if role != old_role:
                        model.token_version += 1
                model.updated_at = utc_now()
        except IntegrityError as exc:
            raise UserEmailExistsError("Email already exists") from exc
        return _profile(model), old_role

    async def set_status(self, user_id: str, status: UserStatus) -> UserProfile | None:
        async with self.sessions.begin() as session:
            active_admin_ids: list[str] | None = None
            if status == UserStatus.DISABLED:
                active_admin_ids = list(
                    (
                        await session.scalars(
                            select(AppUserModel.user_id)
                            .where(
                                AppUserModel.role == ActorRole.ADMIN.value,
                                AppUserModel.status == UserStatus.ACTIVE.value,
                            )
                            .with_for_update()
                        )
                    ).all()
                )
            model = await session.get(AppUserModel, user_id, with_for_update=True)
            if not model:
                return None
            if (
                active_admin_ids is not None
                and model.role == ActorRole.ADMIN.value
                and model.status == UserStatus.ACTIVE.value
                and len(active_admin_ids) <= 1
            ):
                raise UserLastAdminProtectedError("Last active admin is protected")
            if model.status != status.value:
                model.status = status.value
                if status == UserStatus.DISABLED:
                    model.token_version += 1
                else:
                    model.failed_login_count = 0
                    model.locked_until = None
                model.updated_at = utc_now()
        return _profile(model)

    async def active_admin_count(self) -> int:
        async with self.sessions() as session:
            return int(
                await session.scalar(
                    select(func.count())
                    .select_from(AppUserModel)
                    .where(
                        AppUserModel.role == ActorRole.ADMIN.value,
                        AppUserModel.status == UserStatus.ACTIVE.value,
                    )
                )
                or 0
            )

    async def record_login_failure(self, user_id: str) -> bool:
        now = utc_now()
        async with self.sessions.begin() as session:
            model = await session.get(AppUserModel, user_id, with_for_update=True)
            if not model:
                return False
            model.failed_login_count += 1
            locked = model.failed_login_count >= 5
            if locked:
                model.locked_until = now + timedelta(minutes=15)
            model.updated_at = now
            return locked

    async def record_login_success(self, user_id: str) -> AppUserModel:
        now = utc_now()
        async with self.sessions.begin() as session:
            model = await session.get(AppUserModel, user_id, with_for_update=True)
            assert model is not None
            model.failed_login_count = 0
            model.locked_until = None
            model.last_login_at = now
            model.updated_at = now
        return model

    async def replace_password(
        self, user_id: str, password_hash: str, *, must_change_password: bool
    ) -> AppUserModel | None:
        async with self.sessions.begin() as session:
            model = await session.get(AppUserModel, user_id, with_for_update=True)
            if not model:
                return None
            now = utc_now()
            model.password_hash = password_hash
            model.must_change_password = must_change_password
            model.last_password_changed_at = now
            model.token_version += 1
            model.updated_at = now
        return model

    async def increment_token_version(self, user_id: str) -> None:
        async with self.sessions.begin() as session:
            await session.execute(
                update(AppUserModel)
                .where(AppUserModel.user_id == user_id)
                .values(
                    token_version=AppUserModel.token_version + 1,
                    updated_at=utc_now(),
                )
            )


class RefreshSessionRepository:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self.sessions = sessions

    async def create(self, values: dict[str, object]) -> None:
        async with self.sessions.begin() as session:
            session.add(AuthRefreshSessionModel(**values))

    async def rotate(
        self, *, session_id: str, token_hash: str, jti: str, new_values: dict[str, object]
    ) -> tuple[str, str] | None:
        async with self.sessions.begin() as session:
            current = await session.get(AuthRefreshSessionModel, session_id, with_for_update=True)
            if not current or current.token_hash != token_hash or current.jti != jti:
                return None
            if current.revoked_at is not None:
                return current.user_id, current.token_family_id
            now = utc_now()
            if ensure_utc(current.expires_at) <= now:
                return None
            current.revoked_at = now
            current.last_used_at = now
            current.revoke_reason = "rotated"
            session.add(AuthRefreshSessionModel(**new_values))
            return "", ""

    async def get(self, session_id: str) -> AuthRefreshSessionModel | None:
        async with self.sessions() as session:
            return await session.get(AuthRefreshSessionModel, session_id)

    async def revoke(self, session_id: str, reason: str) -> None:
        async with self.sessions.begin() as session:
            await session.execute(
                update(AuthRefreshSessionModel)
                .where(
                    AuthRefreshSessionModel.session_id == session_id,
                    AuthRefreshSessionModel.revoked_at.is_(None),
                )
                .values(revoked_at=utc_now(), revoke_reason=reason)
            )

    async def revoke_user(self, user_id: str, reason: str) -> int:
        async with self.sessions.begin() as session:
            result = cast(
                CursorResult[Any],
                await session.execute(
                    update(AuthRefreshSessionModel)
                    .where(
                        AuthRefreshSessionModel.user_id == user_id,
                        AuthRefreshSessionModel.revoked_at.is_(None),
                    )
                    .values(revoked_at=utc_now(), revoke_reason=reason)
                ),
            )
            return int(result.rowcount or 0)

    async def revoke_family(self, family_id: str, reason: str) -> int:
        async with self.sessions.begin() as session:
            result = cast(
                CursorResult[Any],
                await session.execute(
                    update(AuthRefreshSessionModel)
                    .where(
                        AuthRefreshSessionModel.token_family_id == family_id,
                        AuthRefreshSessionModel.revoked_at.is_(None),
                    )
                    .values(revoked_at=utc_now(), revoke_reason=reason)
                ),
            )
            return int(result.rowcount or 0)
