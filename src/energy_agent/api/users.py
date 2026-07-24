from fastapi import APIRouter, Query, Request

from energy_agent.api.auth import actor_from_request, require_roles
from energy_agent.api.dependencies import UserServiceDependency
from energy_agent.core.context import ActorContext, ActorRole, get_context
from energy_agent.core.ids import new_id
from energy_agent.users.contracts import (
    ResetPasswordRequest,
    UserCreateRequest,
    UserListResponse,
    UserPatchRequest,
    UserProfile,
    UserStatus,
)

router = APIRouter(prefix="/api/v1/users", tags=["users"])


def _actor(request: Request) -> ActorContext:
    actor = actor_from_request(request, explicit=True)
    require_roles(actor, {ActorRole.ADMIN})
    return actor


def _trace_id() -> str:
    context = get_context()
    return context.trace_id if context else new_id()


@router.get("", response_model=UserListResponse)
async def list_users(
    request: Request,
    service: UserServiceDependency,
    q: str | None = None,
    role: ActorRole | None = None,
    status: UserStatus | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = None,
) -> UserListResponse:
    _actor(request)
    return await service.list_users(q=q, role=role, status=status, limit=limit, cursor=cursor)


@router.post("", response_model=UserProfile, status_code=201)
async def create_user(
    payload: UserCreateRequest, request: Request, service: UserServiceDependency
) -> UserProfile:
    return await service.create(payload, _actor(request), _trace_id())


@router.get("/{user_id}", response_model=UserProfile)
async def get_user(user_id: str, request: Request, service: UserServiceDependency) -> UserProfile:
    _actor(request)
    return await service.get(user_id)


@router.patch("/{user_id}", response_model=UserProfile)
async def patch_user(
    user_id: str,
    payload: UserPatchRequest,
    request: Request,
    service: UserServiceDependency,
) -> UserProfile:
    return await service.patch(user_id, payload, _actor(request), _trace_id())


@router.post("/{user_id}/disable", response_model=UserProfile)
async def disable_user(
    user_id: str, request: Request, service: UserServiceDependency
) -> UserProfile:
    return await service.disable(user_id, _actor(request), _trace_id())


@router.post("/{user_id}/enable", response_model=UserProfile)
async def enable_user(
    user_id: str, request: Request, service: UserServiceDependency
) -> UserProfile:
    return await service.enable(user_id, _actor(request), _trace_id())


@router.post("/{user_id}/reset-password", response_model=UserProfile)
async def reset_password(
    user_id: str,
    payload: ResetPasswordRequest,
    request: Request,
    service: UserServiceDependency,
) -> UserProfile:
    return await service.reset_password(
        user_id, payload.temporary_password, _actor(request), _trace_id()
    )


@router.post("/{user_id}/revoke-sessions", response_model=UserProfile)
async def revoke_sessions(
    user_id: str, request: Request, service: UserServiceDependency
) -> UserProfile:
    return await service.revoke_sessions(user_id, _actor(request), _trace_id())
