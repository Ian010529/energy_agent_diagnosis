import re
from collections.abc import Iterable

from fastapi import Request

from energy_agent.core.context import ActorContext, ActorRole
from energy_agent.core.errors import (
    ActorRequiredError,
    ActorRoleInvalidError,
    AuthenticationError,
    PermissionDeniedError,
)


def actor_from_request(request: Request, *, explicit: bool = False) -> ActorContext:
    settings = request.app.state.container.settings
    actor_id = request.headers.get("X-Actor-ID")
    role_value = request.headers.get("X-Actor-Role")
    if settings.auth_mode == "trusted_headers":
        if request.headers.get("X-Internal-API-Key") != settings.internal_api_key:
            raise AuthenticationError("Internal API authentication failed")
        explicit = True
    if not actor_id or not role_value:
        if explicit:
            raise ActorRequiredError("Explicit actor headers are required")
        return ActorContext("local-operator", ActorRole.OPERATOR, settings.auth_mode)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:@-]{0,127}", actor_id):
        raise ActorRequiredError("Actor ID format is invalid")
    if actor_id.startswith("service:") and request.headers.get("X-Service-Actor") != "trusted":
        raise AuthenticationError("Service actors cannot be supplied by external headers")
    try:
        role = ActorRole(role_value)
    except ValueError as exc:
        raise ActorRoleInvalidError("Actor role is invalid") from exc
    return ActorContext(actor_id, role, settings.auth_mode)


def require_roles(actor: ActorContext, roles: Iterable[ActorRole]) -> None:
    if actor.actor_role not in set(roles):
        raise PermissionDeniedError("Actor role does not permit this action")


def require_pilot_write(request: Request, actor: ActorContext) -> None:
    settings = request.app.state.container.settings
    if not settings.pilot_mode:
        return
    allowed = {value.strip() for value in settings.pilot_allowed_actors.split(",") if value.strip()}
    if actor.actor_id not in allowed:
        raise PermissionDeniedError("Actor is not in the pilot write allowlist")
