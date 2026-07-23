from datetime import datetime, timedelta
from typing import Protocol

from energy_agent.core.errors import InvalidRequestError, ResourceNotFoundError
from energy_agent.core.time import utc_now
from energy_agent.evidence.contracts import (
    EvidenceDetail,
    SessionTimeseriesResponse,
    TimeseriesPoint,
    TimeseriesSeries,
)
from energy_agent.evidence.ports import (
    EvidenceCatalogPort,
    EvidenceMemoryPort,
    EvidenceResultPort,
    EvidenceRunPort,
    EvidenceSessionPort,
    EvidenceSourcePort,
)
from energy_agent.templates.registry import TemplateNotFoundError
from energy_agent.templates.routing import DEFAULT_TEMPLATE_REGISTRY

UNITS = {
    "cabinet_temperature": "°C",
    "ambient_temperature": "°C",
    "fan_speed": "rpm",
    "dc_voltage": "V",
    "dc_current": "A",
    "ac_power": "kW",
    "communication_status": None,
}


class TimeseriesPort(Protocol):
    async def query_points(
        self,
        device_id: str,
        metrics: list[str],
        start_time: str,
        end_time: str,
        max_points: int,
        measurements: list[str] | None = None,
    ) -> dict[str, list[tuple[datetime, float, str]]]: ...


class EvidenceService:
    def __init__(
        self,
        *,
        sessions: EvidenceSessionPort,
        results: EvidenceResultPort,
        runs: EvidenceRunPort,
        memory: EvidenceMemoryPort,
        sources: EvidenceSourcePort,
        catalog: EvidenceCatalogPort,
        timeseries: TimeseriesPort,
    ) -> None:
        self.sessions = sessions
        self.results = results
        self.runs = runs
        self.memory = memory
        self.sources = sources
        self.catalog = catalog
        self.timeseries_provider = timeseries

    async def detail(self, session_id: str, evidence_id: str) -> EvidenceDetail:
        session = await self.sessions.get(session_id, trace_id="evidence-query")
        if not session:
            raise ResourceNotFoundError("Diagnosis session not found")
        result = await self.results.latest(session_id)
        evidence = (
            next(
                (item for item in result.evidence if item.evidence_id == evidence_id),
                None,
            )
            if result
            else None
        )
        if not evidence:
            memory = await self.memory.get(session_id, trace_id=session.trace_id)
            evidence = (
                next((item for item in memory.evidence if item.evidence_id == evidence_id), None)
                if memory
                else None
            )
        if not evidence:
            raise ResourceNotFoundError("Evidence does not belong to this session")
        detail: dict[str, object] = {}
        content_excerpt: str | None = None
        title = evidence.source_id
        source_detail = None
        if evidence.source_type == "manual":
            source_detail = await self.sources.manual(evidence.chunk_id or evidence.source_id)
        elif evidence.source_type == "ticket":
            source_detail = await self.sources.ticket(evidence.source_id)
        elif evidence.source_type == "case":
            source_detail = await self.sources.case(evidence.source_id)
        elif evidence.source_type == "timeseries":
            detail["timeseries_descriptor"] = {
                "device_id": session.device_id,
                "metric": evidence.metadata.get("metric"),
                "time_window": evidence.metadata.get("time_window"),
            }
        elif evidence.source_type == "graph":
            content_excerpt = evidence.summary
            title = "关联关系摘要"
        if source_detail:
            title = source_detail.title
            content_excerpt = source_detail.content_excerpt
            detail[source_detail.payload_name] = source_detail.payload
        return EvidenceDetail(
            evidence_id=evidence.evidence_id,
            source_type=evidence.source_type,
            source_id=evidence.source_id,
            title=title,
            summary=evidence.summary,
            citation=evidence.citation,
            verified=evidence.verified,
            scores={
                name: getattr(evidence, name)
                for name in (
                    "retrieval_score",
                    "source_reliability",
                    "verification_score",
                    "freshness_score",
                    "relevance_to_alarm",
                    "final_score",
                )
            },
            metadata=evidence.metadata,
            content_excerpt=content_excerpt,
            **detail,
        )

    async def timeseries(
        self,
        session_id: str,
        run_id: str | None,
        metric: str | None,
        start_time: datetime | None,
        end_time: datetime | None,
    ) -> SessionTimeseriesResponse:
        session = await self.sessions.get(session_id, trace_id="timeseries-query")
        if not session or not session.device_id:
            raise ResourceNotFoundError("Diagnosis session or device not found")
        run = (
            await self.runs.get_for_session(run_id, session_id, trace_id=session.trace_id)
            if run_id
            else await self.runs.latest(session_id, trace_id=session.trace_id)
        )
        if run_id and not run:
            raise ResourceNotFoundError("Run does not belong to this session")
        try:
            template = (
                DEFAULT_TEMPLATE_REGISTRY.get(run.diagnosis_template_id)
                if run and run.diagnosis_template_id
                else None
            )
        except TemplateNotFoundError:
            template = None
        if template is None:
            raise InvalidRequestError("Timeseries template is unavailable")
        allowed = template.metrics if template else []
        metrics = [metric] if metric else allowed
        if not metrics or any(item not in allowed for item in metrics):
            raise InvalidRequestError("Timeseries metric is not allowed")
        memory = await self.memory.get(session_id, trace_id=session.trace_id)
        window = memory.time_window if memory else None
        if start_time or end_time:
            window_source = "requested"
            end = end_time or utc_now()
            start = start_time or end - timedelta(minutes=template.default_window_minutes)
        elif window and window.get("start_time") and window.get("end_time"):
            window_source = "session_memory"
            start = datetime.fromisoformat(str(window["start_time"]))
            end = datetime.fromisoformat(str(window["end_time"]))
        elif session.alarm_id:
            alarm = await self.catalog.alarm(session.alarm_id)
            window_source = "alarm"
            end = alarm.trigger_time
            start = end - timedelta(minutes=template.default_window_minutes)
        else:
            window_source = "current"
            end = utc_now()
            start = end - timedelta(minutes=template.default_window_minutes)
        if start >= end:
            raise InvalidRequestError("Timeseries window is invalid")
        points = await self.timeseries_provider.query_points(
            session.device_id,
            metrics,
            start.isoformat(),
            end.isoformat(),
            1000,
            measurements=template.measurements,
        )
        has_points = any(points.values())
        return SessionTimeseriesResponse(
            device_id=session.device_id,
            start_time=start,
            end_time=end,
            window_source=window_source,
            empty_reason=(None if has_points else "所选时间范围内没有与当前诊断模板匹配的时序点。"),
            series=[
                TimeseriesSeries(
                    metric=name,
                    unit=UNITS.get(name),
                    points=[
                        TimeseriesPoint(timestamp=timestamp, value=value, quality=quality)
                        for timestamp, value, quality in values
                    ],
                )
                for name, values in points.items()
            ],
        )
