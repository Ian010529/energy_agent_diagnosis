from fastapi import Request

from energy_agent.agent.templates.routing import DEFAULT_TEMPLATE_REGISTRY
from energy_agent.catalog.contracts import (
    AlarmItem,
    AlarmListResponse,
    AuthCapability,
    CapabilitiesResponse,
    DatasetCapability,
    DeviceItem,
    DeviceListResponse,
    DiagnosisSessionListResponse,
    SiteListResponse,
    TemplateCapability,
)
from energy_agent.catalog.repository import CatalogRepository


class CatalogService:
    def __init__(self, repository: CatalogRepository, request: Request) -> None:
        self.repository = repository
        self.request = request

    @classmethod
    def from_request(cls, request: Request) -> "CatalogService":
        return cls(request.app.state.catalog_repository, request)

    def capabilities(self) -> CapabilitiesResponse:
        settings = self.request.app.state.settings
        templates = [
            TemplateCapability(
                template_id=item.template_id,
                template_version=item.template_version,
                device_type=item.device_type,
                alarm_category=item.alarm_category,
                alarm_patterns=item.alarm_patterns,
                measurements=item.measurements,
                metrics=item.metrics,
            )
            for item in DEFAULT_TEMPLATE_REGISTRY.templates
        ]
        return CapabilitiesResponse(
            app_version="0.1.0",
            active_dataset=DatasetCapability(id="pilot_medium_v1", version="1.3.0"),
            auth=AuthCapability(mode=settings.auth_mode, pilot_mode=settings.pilot_mode),
            templates=templates,
            device_types=sorted({item.device_type for item in templates}),
            features={
                "graph": settings.graph_mode == "neo4j",
                "model": settings.model_mode != "disabled",
                "reranker": settings.rerank_mode != "disabled",
                "case_review": True,
                "ticket_write": False,
                "oidc": False,
            },
            limits={
                "max_message_length": settings.request_body_max_bytes,
                "max_clarification_questions": 3,
                "max_tool_calls": 8,
            },
        )

    async def sites(self) -> SiteListResponse:
        return SiteListResponse(items=await self.repository.sites())

    async def devices(
        self, filters: dict[str, object], limit: int, cursor: str | None
    ) -> DeviceListResponse:
        items, next_cursor = await self.repository.devices(filters, limit, cursor)
        return DeviceListResponse(
            items=items, next_cursor=next_cursor, has_more=next_cursor is not None
        )

    async def device(self, device_id: str) -> DeviceItem:
        return await self.repository.device(device_id)

    async def alarms(
        self, filters: dict[str, object], limit: int, cursor: str | None
    ) -> AlarmListResponse:
        items, next_cursor = await self.repository.alarms(filters, limit, cursor)
        return AlarmListResponse(
            items=items, next_cursor=next_cursor, has_more=next_cursor is not None
        )

    async def alarm(self, alarm_id: str) -> AlarmItem:
        return await self.repository.alarm(alarm_id)

    async def sessions(
        self, filters: dict[str, object], limit: int, cursor: str | None
    ) -> DiagnosisSessionListResponse:
        items, next_cursor = await self.repository.sessions(filters, limit, cursor)
        return DiagnosisSessionListResponse(
            items=items, next_cursor=next_cursor, has_more=next_cursor is not None
        )
