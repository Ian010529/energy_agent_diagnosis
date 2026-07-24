from dataclasses import dataclass
from datetime import timedelta
from secrets import token_urlsafe
from typing import Any

import jwt

from energy_agent.core.config import Settings
from energy_agent.core.ids import new_id
from energy_agent.core.time import utc_now


@dataclass(frozen=True, slots=True)
class IssuedToken:
    token: str
    jti: str
    expires_in: int


class JWTCodec:
    algorithm = "HS256"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        if settings.auth_mode == "jwt" and (
            not settings.jwt_access_secret or not settings.jwt_refresh_secret
        ):
            raise ValueError("JWT secrets are required")
        self.access_secret = settings.jwt_access_secret or token_urlsafe(48)
        self.refresh_secret = settings.jwt_refresh_secret or token_urlsafe(48)

    def issue_access(
        self, *, user_id: str, username: str, role: str, token_version: int
    ) -> IssuedToken:
        now = utc_now()
        seconds = self.settings.jwt_access_ttl_minutes * 60
        jti = new_id()
        token = jwt.encode(
            {
                "sub": user_id,
                "username": username,
                "role": role,
                "type": "access",
                "token_version": token_version,
                "jti": jti,
                "iss": self.settings.jwt_issuer,
                "aud": self.settings.jwt_access_audience,
                "iat": now,
                "nbf": now,
                "exp": now + timedelta(seconds=seconds),
            },
            self.access_secret,
            algorithm=self.algorithm,
        )
        return IssuedToken(token, jti, seconds)

    def issue_refresh(
        self,
        *,
        user_id: str,
        session_id: str,
        family_id: str,
        jti: str,
        token_version: int,
    ) -> IssuedToken:
        now = utc_now()
        seconds = self.settings.jwt_refresh_ttl_days * 86_400
        token = jwt.encode(
            {
                "sub": user_id,
                "type": "refresh",
                "session_id": session_id,
                "family_id": family_id,
                "jti": jti,
                "token_version": token_version,
                "iss": self.settings.jwt_issuer,
                "aud": self.settings.jwt_refresh_audience,
                "iat": now,
                "nbf": now,
                "exp": now + timedelta(seconds=seconds),
            },
            self.refresh_secret,
            algorithm=self.algorithm,
        )
        return IssuedToken(token, jti, seconds)

    def decode_access(self, token: str) -> dict[str, Any]:
        return self._decode(
            token,
            secret=self.access_secret,
            audience=self.settings.jwt_access_audience,
            token_type="access",
        )

    def decode_refresh(self, token: str) -> dict[str, Any]:
        return self._decode(
            token,
            secret=self.refresh_secret,
            audience=self.settings.jwt_refresh_audience,
            token_type="refresh",
        )

    def _decode(self, token: str, *, secret: str, audience: str, token_type: str) -> dict[str, Any]:
        required = ["sub", "jti", "iss", "aud", "iat", "nbf", "exp", "type", "token_version"]
        required.extend(
            ["username", "role"] if token_type == "access" else ["session_id", "family_id"]
        )
        payload = jwt.decode(
            token,
            secret,
            algorithms=[self.algorithm],
            issuer=self.settings.jwt_issuer,
            audience=audience,
            options={"require": required},
        )
        if payload.get("type") != token_type:
            raise jwt.InvalidTokenError("token type mismatch")
        return payload
