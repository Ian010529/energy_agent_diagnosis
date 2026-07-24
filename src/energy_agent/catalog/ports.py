from typing import Protocol

from energy_agent.catalog.contracts import (
    AlarmRecord,
    DeviceItem,
    DiagnosisSessionItem,
    SiteItem,
)


class CatalogRepositoryPort(Protocol):
    async def sites(self) -> list[SiteItem]: ...

    async def devices(
        self, filters: dict[str, object], limit: int, cursor: str | None
    ) -> tuple[list[DeviceItem], str | None]: ...

    async def device(self, device_id: str) -> DeviceItem: ...

    async def alarms(
        self, filters: dict[str, object], limit: int, cursor: str | None
    ) -> tuple[list[AlarmRecord], str | None]: ...

    async def alarm(self, alarm_id: str) -> AlarmRecord: ...

    async def sessions(
        self, filters: dict[str, object], limit: int, cursor: str | None
    ) -> tuple[list[DiagnosisSessionItem], str | None]: ...
