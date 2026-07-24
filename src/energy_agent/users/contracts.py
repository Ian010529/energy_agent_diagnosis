from datetime import datetime
from enum import StrEnum

from pydantic import Field, model_validator

from energy_agent.contracts.common import StrictModel
from energy_agent.core.context import ActorRole


class UserStatus(StrEnum):
    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"


class UserProfile(StrictModel):
    user_id: str
    username: str
    display_name: str
    email: str | None = None
    role: ActorRole
    status: UserStatus
    must_change_password: bool
    last_login_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class LoginRequest(StrictModel):
    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=128)


class RefreshRequest(StrictModel):
    refresh_token: str = Field(min_length=1)


class LogoutRequest(RefreshRequest):
    pass


class ChangePasswordRequest(StrictModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=1, max_length=128)


class TokenResponse(StrictModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    access_expires_in: int
    refresh_expires_in: int
    user: UserProfile


class UserCreateRequest(StrictModel):
    username: str = Field(min_length=1, max_length=128)
    display_name: str = Field(min_length=1, max_length=128)
    email: str | None = Field(default=None, max_length=255)
    role: ActorRole
    initial_password: str = Field(min_length=1, max_length=128)


class UserPatchRequest(StrictModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=128)
    email: str | None = Field(default=None, max_length=255)
    role: ActorRole | None = None

    @model_validator(mode="after")
    def require_change(self) -> "UserPatchRequest":
        if not self.model_fields_set:
            raise ValueError("At least one field is required")
        return self


class ResetPasswordRequest(StrictModel):
    temporary_password: str = Field(min_length=1, max_length=128)


class UserListResponse(StrictModel):
    items: list[UserProfile]
    next_cursor: str | None = None
    has_more: bool = False
