from fastapi import APIRouter, Request

from energy_agent.api.auth import actor_from_request
from energy_agent.api.dependencies import AuthServiceDependency
from energy_agent.core.context import get_context
from energy_agent.core.ids import new_id
from energy_agent.users.contracts import (
    ChangePasswordRequest,
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    TokenResponse,
    UserProfile,
)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def _trace_id() -> str:
    context = get_context()
    return context.trace_id if context else new_id()


def _client(request: Request) -> tuple[str | None, str | None]:
    forwarded = request.headers.get("x-forwarded-for")
    ip = (
        forwarded.split(",", 1)[0].strip()
        if forwarded
        else (request.client.host if request.client else None)
    )
    return ip, request.headers.get("user-agent")


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: LoginRequest, request: Request, service: AuthServiceDependency
) -> TokenResponse:
    ip, user_agent = _client(request)
    return await service.login(
        payload.username,
        payload.password,
        trace_id=_trace_id(),
        ip=ip,
        user_agent=user_agent,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    payload: RefreshRequest, request: Request, service: AuthServiceDependency
) -> TokenResponse:
    ip, user_agent = _client(request)
    return await service.refresh(
        payload.refresh_token,
        trace_id=_trace_id(),
        ip=ip,
        user_agent=user_agent,
    )


@router.get("/me", response_model=UserProfile)
async def me(request: Request, service: AuthServiceDependency) -> UserProfile:
    actor = actor_from_request(request)
    return await service.current_user(actor.actor_id)


@router.post("/change-password", response_model=TokenResponse)
async def change_password(
    payload: ChangePasswordRequest,
    request: Request,
    service: AuthServiceDependency,
) -> TokenResponse:
    ip, user_agent = _client(request)
    return await service.change_password(
        actor_from_request(request),
        payload.current_password,
        payload.new_password,
        trace_id=_trace_id(),
        ip=ip,
        user_agent=user_agent,
    )


@router.post("/logout", status_code=204)
async def logout(payload: LogoutRequest, request: Request, service: AuthServiceDependency) -> None:
    await service.logout(actor_from_request(request), payload.refresh_token, _trace_id())


@router.post("/logout-all", status_code=204)
async def logout_all(request: Request, service: AuthServiceDependency) -> None:
    await service.logout_all(actor_from_request(request), _trace_id())
