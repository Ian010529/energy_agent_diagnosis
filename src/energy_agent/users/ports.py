from datetime import datetime
from typing import Any, Protocol

from energy_agent.core.context import ActorContext, ActorRole, ServiceActorContext
from energy_agent.users.contracts import UserProfile, UserStatus


class AuthUserRecord(Protocol):
    user_id: str
    username: str
    role: str
    status: str
    token_version: int
    password_hash: str
    locked_until: datetime | None


class UserRepositoryPort(Protocol):
    async def by_normalized_username(self, username: str) -> AuthUserRecord | None: ...

    async def by_id(self, user_id: str) -> AuthUserRecord | None: ...

    async def profile(self, user_id: str) -> UserProfile | None: ...

    async def create(self, values: dict[str, object]) -> UserProfile: ...

    async def list(
        self,
        *,
        q: str | None,
        role: ActorRole | None,
        status: UserStatus | None,
        limit: int,
        cursor: str | None,
    ) -> tuple[list[UserProfile], bool]: ...

    async def update_profile(
        self,
        user_id: str,
        *,
        display_name: str | None,
        email: str | None,
        email_set: bool,
        role: ActorRole | None,
    ) -> tuple[UserProfile | None, ActorRole | None]: ...

    async def set_status(self, user_id: str, status: UserStatus) -> UserProfile | None: ...

    async def active_admin_count(self) -> int: ...

    async def record_login_failure(self, user_id: str) -> bool: ...

    async def record_login_success(self, user_id: str) -> AuthUserRecord: ...

    async def replace_password(
        self, user_id: str, password_hash: str, *, must_change_password: bool
    ) -> AuthUserRecord | None: ...

    async def increment_token_version(self, user_id: str) -> None: ...


class RefreshSessionPort(Protocol):
    async def create(self, values: dict[str, object]) -> None: ...

    async def rotate(
        self,
        *,
        session_id: str,
        token_hash: str,
        jti: str,
        new_values: dict[str, object],
    ) -> tuple[str, str] | None: ...

    async def revoke(self, session_id: str, reason: str) -> None: ...

    async def revoke_user(self, user_id: str, reason: str) -> int: ...

    async def revoke_family(self, family_id: str, reason: str) -> int: ...


class UserAuditPort(Protocol):
    async def write(
        self,
        *,
        actor: ActorContext | ServiceActorContext,
        action: str,
        resource_type: str,
        resource_id: str,
        trace_id: str,
        outcome: str = "succeeded",
        session_id: str | None = None,
        case_id: str | None = None,
        snapshot: dict[str, Any] | None = None,
    ) -> None: ...
