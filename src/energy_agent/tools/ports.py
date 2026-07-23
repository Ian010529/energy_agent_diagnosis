from typing import Protocol

from energy_agent.retrieval.ports import RetrievalCandidatePort


class DeviceAlarmPort(Protocol):
    async def get_device(self, device_id: str) -> dict[str, object] | None: ...

    async def get_alarm(self, alarm_id: str, device_id: str | None) -> dict[str, object] | None: ...


class OperationalDataPort(DeviceAlarmPort, RetrievalCandidatePort, Protocol):
    pass


class TimeseriesPort(Protocol):
    async def query(
        self,
        device_id: str,
        metrics: list[str],
        start_time: str,
        end_time: str,
        max_points: int,
        measurements: list[str] | None = None,
    ) -> dict[str, object]: ...
