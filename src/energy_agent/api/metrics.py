from fastapi import APIRouter, Request
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from energy_agent.core.errors import AuthenticationError

router = APIRouter()


@router.get("/metrics", include_in_schema=False)
async def metrics(request: Request) -> Response:
    settings = request.app.state.settings
    if settings.app_env not in {"local", "test"}:
        bearer = request.headers.get("Authorization", "").removeprefix("Bearer ")
        if (
            request.headers.get("X-Internal-API-Key") != settings.internal_api_key
            and bearer != settings.internal_api_key
        ):
            raise AuthenticationError("Internal metrics authentication failed")
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
