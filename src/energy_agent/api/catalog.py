from datetime import datetime

from fastapi import APIRouter, Query, Request

from energy_agent.api.auth import actor_from_request, require_roles
from energy_agent.catalog.contracts import (
    AlarmItem,
    AlarmListResponse,
    CapabilitiesResponse,
    DeviceItem,
    DeviceListResponse,
    SiteListResponse,
)
from energy_agent.catalog.service import CatalogService
from energy_agent.core.context import ActorRole

router = APIRouter(prefix="/api/v1", tags=["catalog"])
READ_ROLES = {ActorRole.VIEWER, ActorRole.OPERATOR, ActorRole.REVIEWER, ActorRole.ADMIN}


def _authorize(request: Request) -> None:
    require_roles(actor_from_request(request), READ_ROLES)


@router.get("/capabilities", response_model=CapabilitiesResponse)
async def capabilities(request: Request) -> CapabilitiesResponse:
    _authorize(request)
    return CatalogService.from_request(request).capabilities()


@router.get("/sites", response_model=SiteListResponse)
async def sites(request: Request) -> SiteListResponse:
    _authorize(request)
    return await CatalogService.from_request(request).sites()


@router.get("/devices", response_model=DeviceListResponse)
async def devices(
    request: Request,
    site_id: str | None = None,
    device_type: str | None = None,
    device_model: str | None = None,
    manufacturer: str | None = None,
    status: str | None = None,
    q: str | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = None,
) -> DeviceListResponse:
    _authorize(request)
    values = locals()
    filters = {
        name: values[name]
        for name in (
            "site_id",
            "device_type",
            "device_model",
            "manufacturer",
            "status",
            "q",
        )
        if values[name] is not None
    }
    return await CatalogService.from_request(request).devices(filters, limit, cursor)


@router.get("/devices/{device_id}", response_model=DeviceItem)
async def device(device_id: str, request: Request) -> DeviceItem:
    _authorize(request)
    return await CatalogService.from_request(request).device(device_id)


@router.get("/alarms", response_model=AlarmListResponse)
async def alarms(
    request: Request,
    site_id: str | None = None,
    device_id: str | None = None,
    alarm_level: str | None = None,
    status: str | None = None,
    source_system: str | None = None,
    supported: bool | None = None,
    template_id: str | None = None,
    from_time: datetime | None = None,
    to_time: datetime | None = None,
    q: str | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = None,
) -> AlarmListResponse:
    _authorize(request)
    values = locals()
    names = (
        "site_id",
        "device_id",
        "alarm_level",
        "status",
        "source_system",
        "supported",
        "template_id",
        "from_time",
        "to_time",
        "q",
    )
    filters = {name: values[name] for name in names if values[name] is not None}
    return await CatalogService.from_request(request).alarms(filters, limit, cursor)


@router.get("/alarms/{alarm_id}", response_model=AlarmItem)
async def alarm(alarm_id: str, request: Request) -> AlarmItem:
    _authorize(request)
    return await CatalogService.from_request(request).alarm(alarm_id)
