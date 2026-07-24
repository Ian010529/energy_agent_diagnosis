import hashlib
from datetime import timedelta

import jwt

from energy_agent.core.config import Settings
from energy_agent.core.context import ActorContext, ActorRole, ServiceActorContext
from energy_agent.core.errors import (
    AuthAccountLockedError,
    AuthCurrentPasswordInvalidError,
    AuthInvalidCredentialsError,
    AuthRefreshExpiredError,
    AuthRefreshInvalidError,
    AuthRefreshReusedError,
    AuthTokenExpiredError,
    AuthTokenInvalidError,
    InvalidRequestError,
    RateLimitExceededError,
    UserNotFoundError,
    UserSelfDisableForbiddenError,
    UserSelfRoleChangeForbiddenError,
)
from energy_agent.core.ids import new_id
from energy_agent.core.time import ensure_utc, utc_now
from energy_agent.observability.metrics import (
    AUTH_ATTEMPTS,
    AUTH_REFRESH,
    AUTH_SESSIONS_REVOKED,
    USER_ADMIN_ACTIONS,
)
from energy_agent.reliability.rate_limit import RateLimiter
from energy_agent.users.contracts import (
    TokenResponse,
    UserCreateRequest,
    UserListResponse,
    UserPatchRequest,
    UserProfile,
    UserStatus,
)
from energy_agent.users.jwt import JWTCodec
from energy_agent.users.password import (
    dummy_verify,
    hash_password,
    normalize_username,
    validate_password,
    verify_password,
)
from energy_agent.users.ports import (
    AuthUserRecord,
    RefreshSessionPort,
    UserAuditPort,
    UserRepositoryPort,
)
from energy_agent.users.tokens import token_digest


def _client_hash(value: str | None) -> str | None:
    return hashlib.sha256(value.encode()).hexdigest() if value else None


class AuthService:
    def __init__(
        self,
        users: UserRepositoryPort,
        sessions: RefreshSessionPort,
        audit: UserAuditPort,
        codec: JWTCodec,
        rate_limiter: RateLimiter,
        settings: Settings,
    ) -> None:
        self.users = users
        self.sessions = sessions
        self.audit = audit
        self.codec = codec
        self.rate_limiter = rate_limiter
        self.settings = settings

    async def login(
        self, username: str, password: str, *, trace_id: str, ip: str | None, user_agent: str | None
    ) -> TokenResponse:
        normalized = normalize_username(username)
        if self.settings.rate_limit_enabled:
            username_key = hashlib.sha256(normalized.encode()).hexdigest()
            source_key = hashlib.sha256((ip or "unknown").encode()).hexdigest()
            username_allowed, _ = await self.rate_limiter.allow(
                username_key,
                "auth_login_username",
                self.settings.rate_limit_auth_login_username,
                300,
            )
            source_allowed, _ = await self.rate_limiter.allow(
                source_key,
                "auth_login_source",
                self.settings.rate_limit_auth_login_source,
                300,
            )
            if not username_allowed or not source_allowed:
                raise RateLimitExceededError("账号暂时不可用，请稍后重试")
        user = await self.users.by_normalized_username(normalized)
        if not user:
            dummy_verify(password)
            AUTH_ATTEMPTS.labels(outcome="failed").inc()
            await self._audit_service(
                "auth.login.failed",
                hashlib.sha256(normalized.encode()).hexdigest(),
                trace_id,
                "failed",
            )
            raise AuthInvalidCredentialsError("用户名或密码错误")
        now = utc_now()
        if user.locked_until and ensure_utc(user.locked_until) > now:
            AUTH_ATTEMPTS.labels(outcome="locked").inc()
            await self._audit_service(
                "auth.login.locked",
                hashlib.sha256(normalized.encode()).hexdigest(),
                trace_id,
                "failed",
            )
            raise AuthAccountLockedError("账号暂时不可用，请稍后重试")
        valid = verify_password(password, user.password_hash)
        if not valid or user.status != UserStatus.ACTIVE.value:
            locked = await self.users.record_login_failure(user.user_id) if not valid else False
            AUTH_ATTEMPTS.labels(outcome="failed").inc()
            await self._audit_service(
                "auth.login.failed",
                hashlib.sha256(normalized.encode()).hexdigest(),
                trace_id,
                "failed",
            )
            if locked:
                raise AuthAccountLockedError("账号暂时不可用，请稍后重试")
            raise AuthInvalidCredentialsError("用户名或密码错误")
        user = await self.users.record_login_success(user.user_id)
        response = await self._issue_pair(user, ip=ip, user_agent=user_agent)
        AUTH_ATTEMPTS.labels(outcome="succeeded").inc()
        await self.audit.write(
            actor=ActorContext(user.user_id, ActorRole(user.role), "jwt"),
            action="auth.login.succeeded",
            resource_type="user",
            resource_id=user.user_id,
            trace_id=trace_id,
        )
        return response

    async def authenticate_access(self, token: str) -> tuple[ActorContext, UserProfile]:
        try:
            claims = self.codec.decode_access(token)
        except jwt.ExpiredSignatureError as exc:
            raise AuthTokenExpiredError("Access token expired") from exc
        except jwt.PyJWTError as exc:
            raise AuthTokenInvalidError("Access token invalid") from exc
        user = await self.users.by_id(str(claims["sub"]))
        if (
            not user
            or user.status != UserStatus.ACTIVE.value
            or user.token_version != claims.get("token_version")
            or user.role != claims.get("role")
        ):
            raise AuthTokenInvalidError("Access token invalid")
        return ActorContext(user.user_id, ActorRole(user.role), "jwt"), await self.current_user(
            user.user_id
        )

    async def current_user(self, user_id: str) -> UserProfile:
        profile = await self.users.profile(user_id)
        if not profile:
            raise UserNotFoundError("User not found")
        return profile

    async def refresh(
        self, refresh_token: str, *, trace_id: str, ip: str | None, user_agent: str | None
    ) -> TokenResponse:
        if self.settings.rate_limit_enabled:
            allowed, _ = await self.rate_limiter.allow(
                hashlib.sha256((ip or "unknown").encode()).hexdigest(),
                "auth_refresh",
                self.settings.rate_limit_auth_refresh_per_minute,
            )
            if not allowed:
                raise RateLimitExceededError("Refresh rate limit exceeded")
        try:
            claims = self.codec.decode_refresh(refresh_token)
        except jwt.ExpiredSignatureError as exc:
            AUTH_REFRESH.labels(outcome="expired").inc()
            await self._audit_service("auth.refresh.failed", "expired", trace_id, "failed")
            raise AuthRefreshExpiredError("Refresh token expired") from exc
        except jwt.PyJWTError as exc:
            AUTH_REFRESH.labels(outcome="invalid").inc()
            await self._audit_service("auth.refresh.failed", "invalid", trace_id, "failed")
            raise AuthRefreshInvalidError("Refresh token invalid") from exc
        user = await self.users.by_id(str(claims["sub"]))
        if (
            not user
            or user.status != UserStatus.ACTIVE.value
            or user.token_version != claims.get("token_version")
        ):
            await self._audit_service(
                "auth.refresh.failed", user.user_id if user else "unknown", trace_id, "failed"
            )
            raise AuthRefreshInvalidError("Refresh token invalid")
        new_session_id = new_id()
        new_jti = new_id()
        issued_refresh = self.codec.issue_refresh(
            user_id=user.user_id,
            session_id=new_session_id,
            family_id=str(claims["family_id"]),
            jti=new_jti,
            token_version=user.token_version,
        )
        now = utc_now()
        result = await self.sessions.rotate(
            session_id=str(claims["session_id"]),
            token_hash=token_digest(refresh_token),
            jti=str(claims["jti"]),
            new_values={
                "session_id": new_session_id,
                "user_id": user.user_id,
                "token_hash": token_digest(issued_refresh.token),
                "token_family_id": str(claims["family_id"]),
                "jti": new_jti,
                "rotated_from_session_id": str(claims["session_id"]),
                "created_at": now,
                "expires_at": now + timedelta(seconds=issued_refresh.expires_in),
                "ip_hash": _client_hash(ip),
                "user_agent_hash": _client_hash(user_agent),
            },
        )
        if result is None:
            await self._audit_service("auth.refresh.failed", user.user_id, trace_id, "failed")
            raise AuthRefreshInvalidError("Refresh token invalid")
        if result != ("", ""):
            reused_user, family = result
            count = await self.sessions.revoke_family(family, "reuse_detected")
            await self.users.increment_token_version(reused_user)
            AUTH_SESSIONS_REVOKED.labels(reason_category="reuse").inc(count)
            AUTH_REFRESH.labels(outcome="reused").inc()
            await self._audit_service(
                "auth.refresh.reuse_detected", reused_user, trace_id, "failed"
            )
            raise AuthRefreshReusedError("Refresh token reuse detected")
        access = self.codec.issue_access(
            user_id=user.user_id,
            username=user.username,
            role=user.role,
            token_version=user.token_version,
        )
        AUTH_REFRESH.labels(outcome="succeeded").inc()
        await self.audit.write(
            actor=ActorContext(user.user_id, ActorRole(user.role), "jwt"),
            action="auth.refresh.succeeded",
            resource_type="auth_session",
            resource_id=new_session_id,
            trace_id=trace_id,
        )
        return TokenResponse(
            access_token=access.token,
            refresh_token=issued_refresh.token,
            access_expires_in=access.expires_in,
            refresh_expires_in=issued_refresh.expires_in,
            user=await self.current_user(user.user_id),
        )

    async def change_password(
        self,
        actor: ActorContext,
        current_password: str,
        new_password: str,
        *,
        trace_id: str,
        ip: str | None,
        user_agent: str | None,
    ) -> TokenResponse:
        user = await self.users.by_id(actor.actor_id)
        if not user or not verify_password(current_password, user.password_hash):
            dummy_verify(current_password)
            raise AuthCurrentPasswordInvalidError("Current password is invalid")
        validate_password(new_password, user.username)
        if verify_password(new_password, user.password_hash):
            from energy_agent.core.errors import AuthNewPasswordInvalidError

            raise AuthNewPasswordInvalidError("New password must differ from current password")
        updated = await self.users.replace_password(
            user.user_id, hash_password(new_password, user.username), must_change_password=False
        )
        assert updated is not None
        count = await self.sessions.revoke_user(user.user_id, "password_changed")
        AUTH_SESSIONS_REVOKED.labels(reason_category="password_changed").inc(count)
        await self.audit.write(
            actor=actor,
            action="auth.password.changed",
            resource_type="user",
            resource_id=user.user_id,
            trace_id=trace_id,
        )
        return await self._issue_pair(updated, ip=ip, user_agent=user_agent)

    async def logout(self, actor: ActorContext, refresh_token: str, trace_id: str) -> None:
        try:
            claims = self.codec.decode_refresh(refresh_token)
        except jwt.PyJWTError:
            claims = None
        if claims and claims.get("sub") == actor.actor_id:
            await self.sessions.revoke(str(claims["session_id"]), "logout")
        await self.audit.write(
            actor=actor,
            action="auth.logout",
            resource_type="user",
            resource_id=actor.actor_id,
            trace_id=trace_id,
        )

    async def logout_all(self, actor: ActorContext, trace_id: str) -> None:
        count = await self.sessions.revoke_user(actor.actor_id, "logout_all")
        await self.users.increment_token_version(actor.actor_id)
        AUTH_SESSIONS_REVOKED.labels(reason_category="logout_all").inc(count)
        await self.audit.write(
            actor=actor,
            action="auth.logout_all",
            resource_type="user",
            resource_id=actor.actor_id,
            trace_id=trace_id,
        )

    async def _issue_pair(
        self, user: AuthUserRecord, *, ip: str | None, user_agent: str | None
    ) -> TokenResponse:
        user_id = user.user_id
        token_version = user.token_version
        access = self.codec.issue_access(
            user_id=user_id,
            username=user.username,
            role=user.role,
            token_version=token_version,
        )
        session_id, family_id, jti = new_id(), new_id(), new_id()
        refresh = self.codec.issue_refresh(
            user_id=user_id,
            session_id=session_id,
            family_id=family_id,
            jti=jti,
            token_version=token_version,
        )
        now = utc_now()
        await self.sessions.create(
            {
                "session_id": session_id,
                "user_id": user_id,
                "token_hash": token_digest(refresh.token),
                "token_family_id": family_id,
                "jti": jti,
                "created_at": now,
                "expires_at": now + timedelta(seconds=refresh.expires_in),
                "ip_hash": _client_hash(ip),
                "user_agent_hash": _client_hash(user_agent),
            }
        )
        return TokenResponse(
            access_token=access.token,
            refresh_token=refresh.token,
            access_expires_in=access.expires_in,
            refresh_expires_in=refresh.expires_in,
            user=await self.current_user(user_id),
        )

    async def _audit_service(
        self, action: str, resource_id: str, trace_id: str, outcome: str
    ) -> None:
        await self.audit.write(
            actor=ServiceActorContext("service:auth"),
            action=action,
            resource_type="auth",
            resource_id=resource_id[:64],
            trace_id=trace_id,
            outcome=outcome,
            snapshot={"username_hash": hashlib.sha256(resource_id.encode()).hexdigest()},
        )


class UserService:
    def __init__(
        self, users: UserRepositoryPort, sessions: RefreshSessionPort, audit: UserAuditPort
    ) -> None:
        self.users = users
        self.sessions = sessions
        self.audit = audit

    async def list_users(
        self,
        *,
        q: str | None,
        role: ActorRole | None,
        status: UserStatus | None,
        limit: int,
        cursor: str | None,
    ) -> UserListResponse:
        items, has_more = await self.users.list(
            q=normalize_username(q) if q else None,
            role=role,
            status=status,
            limit=limit,
            cursor=cursor,
        )
        return UserListResponse(
            items=items,
            next_cursor=items[-1].user_id if has_more and items else None,
            has_more=has_more,
        )

    async def get(self, user_id: str) -> UserProfile:
        profile = await self.users.profile(user_id)
        if not profile:
            raise UserNotFoundError("User not found")
        return profile

    async def create(
        self, payload: UserCreateRequest, actor: ActorContext, trace_id: str
    ) -> UserProfile:
        now = utc_now()
        normalized = normalize_username(payload.username)
        display_name = payload.display_name.strip()
        if not normalized or not display_name:
            raise InvalidRequestError("Username and display name must not be blank")
        profile = await self.users.create(
            {
                "user_id": new_id(),
                "username": payload.username.strip(),
                "username_normalized": normalized,
                "display_name": display_name,
                "email": payload.email.strip() or None if payload.email is not None else None,
                "role": payload.role.value,
                "status": UserStatus.ACTIVE.value,
                "password_hash": hash_password(payload.initial_password, payload.username),
                "must_change_password": True,
                "token_version": 1,
                "failed_login_count": 0,
                "created_by": actor.actor_id,
                "created_at": now,
                "updated_at": now,
            }
        )
        await self._audit(actor, "user.created", profile.user_id, trace_id)
        return profile

    async def patch(
        self, user_id: str, payload: UserPatchRequest, actor: ActorContext, trace_id: str
    ) -> UserProfile:
        await self.get(user_id)
        if payload.display_name is not None and not payload.display_name.strip():
            raise InvalidRequestError("Display name must not be blank")
        if actor.actor_id == user_id and payload.role and payload.role != ActorRole.ADMIN:
            raise UserSelfRoleChangeForbiddenError("Admin cannot change own role")
        profile, old_role = await self.users.update_profile(
            user_id,
            display_name=payload.display_name.strip() if payload.display_name else None,
            email=payload.email.strip() if payload.email else payload.email,
            email_set="email" in payload.model_fields_set,
            role=payload.role,
        )
        if not profile:
            raise UserNotFoundError("User not found")
        action = (
            "user.role_changed"
            if payload.role and payload.role != old_role
            else "user.profile_updated"
        )
        if action == "user.role_changed":
            count = await self.sessions.revoke_user(user_id, "role_changed")
            AUTH_SESSIONS_REVOKED.labels(reason_category="role_changed").inc(count)
        await self._audit(
            actor,
            action,
            user_id,
            trace_id,
            snapshot={
                "old_role": old_role.value if old_role else None,
                "new_role": profile.role.value,
            },
        )
        return profile

    async def disable(self, user_id: str, actor: ActorContext, trace_id: str) -> UserProfile:
        if actor.actor_id == user_id:
            raise UserSelfDisableForbiddenError("Admin cannot disable own account")
        await self.get(user_id)
        profile = await self.users.set_status(user_id, UserStatus.DISABLED)
        assert profile is not None
        count = await self.sessions.revoke_user(user_id, "disabled")
        AUTH_SESSIONS_REVOKED.labels(reason_category="disabled").inc(count)
        await self._audit(actor, "user.disabled", user_id, trace_id)
        return profile

    async def enable(self, user_id: str, actor: ActorContext, trace_id: str) -> UserProfile:
        profile = await self.users.set_status(user_id, UserStatus.ACTIVE)
        if not profile:
            raise UserNotFoundError("User not found")
        await self._audit(actor, "user.enabled", user_id, trace_id)
        return profile

    async def reset_password(
        self, user_id: str, password: str, actor: ActorContext, trace_id: str
    ) -> UserProfile:
        current = await self.get(user_id)
        model = await self.users.replace_password(
            user_id, hash_password(password, current.username), must_change_password=True
        )
        assert model is not None
        count = await self.sessions.revoke_user(user_id, "password_reset")
        AUTH_SESSIONS_REVOKED.labels(reason_category="password_reset").inc(count)
        await self._audit(actor, "user.password_reset", user_id, trace_id)
        return await self.get(user_id)

    async def revoke_sessions(
        self, user_id: str, actor: ActorContext, trace_id: str
    ) -> UserProfile:
        await self.get(user_id)
        count = await self.sessions.revoke_user(user_id, "admin_revoked")
        AUTH_SESSIONS_REVOKED.labels(reason_category="admin_revoked").inc(count)
        await self.users.increment_token_version(user_id)
        await self._audit(actor, "user.sessions_revoked", user_id, trace_id)
        return await self.get(user_id)

    async def _audit(
        self,
        actor: ActorContext,
        action: str,
        user_id: str,
        trace_id: str,
        snapshot: dict[str, object] | None = None,
    ) -> None:
        USER_ADMIN_ACTIONS.labels(action=action, outcome="succeeded").inc()
        await self.audit.write(
            actor=actor,
            action=action,
            resource_type="user",
            resource_id=user_id,
            trace_id=trace_id,
            snapshot={"target_user_id": user_id, **(snapshot or {})},
        )
