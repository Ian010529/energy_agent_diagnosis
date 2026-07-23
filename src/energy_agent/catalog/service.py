from energy_agent.catalog.contracts import (
    AlarmItem,
    AlarmListResponse,
    AlarmRecord,
    AuthCapability,
    CapabilitiesResponse,
    DatasetCapability,
    DeviceItem,
    DeviceListResponse,
    DiagnosisSessionListResponse,
    SiteListResponse,
    TemplateCapability,
)
from energy_agent.catalog.repository import CatalogRepository, encode_cursor
from energy_agent.core.config import Settings
from energy_agent.templates.registry import TemplateAmbiguousError, TemplateNotFoundError
from energy_agent.templates.routing import DEFAULT_TEMPLATE_REGISTRY, route_template


def alarm_support(
    device_type: str | None, alarm_name: str
) -> tuple[str | None, str | None, str | None]:
    try:
        template, _ = route_template(device_type=device_type, alarm_name=alarm_name)
    except (TemplateNotFoundError, TemplateAmbiguousError):
        return None, None, None
    return template.alarm_category, template.template_id, template.template_version


def map_alarm(record: AlarmRecord) -> AlarmItem:
    category, template_id, version = alarm_support(record.device_type, record.alarm_name)
    return AlarmItem(
        **record.model_dump(exclude={"device_type"}),
        alarm_category=category,
        supported=template_id is not None,
        template_id=template_id,
        template_version=version,
    )


class CatalogService:
    def __init__(self, repository: CatalogRepository, settings: Settings) -> None:
        self.repository = repository
        self.settings = settings

    def capabilities(self) -> CapabilitiesResponse:
        settings = self.settings
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
        items: list[AlarmItem] = []
        batch_cursor = cursor
        query_filters = {
            key: value for key, value in filters.items() if key not in {"supported", "template_id"}
        }
        while len(items) <= limit:
            records, page_cursor = await self.repository.alarms(
                query_filters, max(100, limit * 2), batch_cursor
            )
            for record in records:
                item = map_alarm(record)
                supported = filters.get("supported")
                if supported is not None and item.supported is not supported:
                    continue
                if filters.get("template_id") and item.template_id != filters["template_id"]:
                    continue
                items.append(item)
                if len(items) > limit:
                    break
            if len(items) > limit or not page_cursor:
                break
            batch_cursor = page_cursor
        has_more = len(items) > limit
        items = items[:limit]
        next_cursor = (
            encode_cursor(f"{items[-1].trigger_time.isoformat()}|{items[-1].alarm_id}")
            if has_more and items
            else None
        )
        return AlarmListResponse(items=items, next_cursor=next_cursor, has_more=has_more)

    async def alarm(self, alarm_id: str) -> AlarmItem:
        return map_alarm(await self.repository.alarm(alarm_id))

    async def sessions(
        self, filters: dict[str, object], limit: int, cursor: str | None
    ) -> DiagnosisSessionListResponse:
        items, next_cursor = await self.repository.sessions(filters, limit, cursor)
        return DiagnosisSessionListResponse(
            items=items, next_cursor=next_cursor, has_more=next_cursor is not None
        )
