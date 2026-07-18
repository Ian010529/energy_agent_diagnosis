from typing import Any, cast

from pydantic import BaseModel

from energy_agent.observability.tracing import Tracer
from energy_agent.providers.influxdb import InfluxTimeseriesProvider
from energy_agent.providers.mysql import MySQLDiagnosisProvider
from energy_agent.retrieval.contracts import RetrievalMode, SourceType
from energy_agent.retrieval.service import RetrievalService
from energy_agent.tools.contracts import (
    AlarmDetailInput,
    DeviceProfileInput,
    ManualSearchInput,
    TicketSearchInput,
    TimeseriesWindowInput,
    ToolMeta,
    ToolResult,
    ToolStatus,
)
from energy_agent.tools.registry import ToolRegistry


def _result(
    trace_id: str,
    data: object,
    *,
    source_system: str,
    partial: bool = False,
    warnings: list[str] | None = None,
    retrieval_mode: str | None = None,
) -> ToolResult:
    empty = data is None or data == [] or data == {}
    return ToolResult(
        success=not empty,
        status=(
            ToolStatus.NOT_FOUND
            if empty
            else ToolStatus.PARTIAL_SUCCESS
            if partial
            else ToolStatus.OK
        ),
        data=data,
        meta=ToolMeta(
            trace_id=trace_id,
            source_system=source_system,
            partial_result=partial,
            retrieval_mode=retrieval_mode,
        ),
        error_code="NOT_FOUND" if empty else "",
        error_message="No matching data" if empty else "",
        warnings=warnings or [],
    )


def build_registry(
    mysql: MySQLDiagnosisProvider,
    influx: InfluxTimeseriesProvider,
    tracer: Tracer | None = None,
    retrieval: RetrievalService | None = None,
) -> ToolRegistry:
    registry = ToolRegistry()
    retrieval_service = retrieval or RetrievalService(mysql=mysql, tracer=cast(Tracer, tracer))

    async def device(payload: BaseModel) -> ToolResult:
        request = cast(DeviceProfileInput, payload)
        return _result(
            request.context.trace_id,
            await mysql.get_device(request.device_id),
            source_system="mysql",
        )

    async def alarm(payload: BaseModel) -> ToolResult:
        request = cast(AlarmDetailInput, payload)
        return _result(
            request.context.trace_id,
            await mysql.get_alarm(request.alarm_id, request.device_id),
            source_system="mysql",
        )

    async def timeseries(payload: BaseModel) -> ToolResult:
        request = cast(TimeseriesWindowInput, payload)
        data = cast(
            dict[str, dict[str, Any]],
            await influx.query(
                request.device_id,
                request.metrics,
                request.start_time,
                request.end_time,
                request.max_points,
            ),
        )
        if not any(not summary.get("missing", True) for summary in data.values()):
            return _result(request.context.trace_id, None, source_system="influxdb")
        return _result(request.context.trace_id, data, source_system="influxdb")

    async def manual(payload: BaseModel) -> ToolResult:
        request = cast(ManualSearchInput, payload)
        mode = (
            RetrievalMode.KEYWORD_ONLY
            if retrieval_service.default_mode == RetrievalMode.KEYWORD_ONLY
            else RetrievalMode(request.retrieval_mode)
        )
        result = await retrieval_service.search(
            SourceType.MANUAL,
            request.query,
            request.filters.model_dump(exclude_none=True),
            trace_id=request.context.trace_id,
            mode=mode,
            top_k=request.top_k,
            score_threshold=request.score_threshold,
        )
        metadata = result.retrieval_metadata
        return _result(
            request.context.trace_id,
            result.model_dump(mode="json"),
            source_system="retrieval",
            partial=metadata.partial_result,
            warnings=metadata.degraded_components,
            retrieval_mode=metadata.retrieval_mode,
        )

    async def tickets(payload: BaseModel) -> ToolResult:
        request = cast(TicketSearchInput, payload)
        mode = (
            RetrievalMode.KEYWORD_ONLY
            if retrieval_service.default_mode == RetrievalMode.KEYWORD_ONLY
            else RetrievalMode(request.retrieval_mode)
        )
        ticket_result = await retrieval_service.search(
            SourceType.TICKET,
            request.query,
            request.filters.model_dump(exclude_none=True),
            trace_id=request.context.trace_id,
            mode=mode,
            top_k=request.top_k,
            score_threshold=request.score_threshold,
            verified_only=request.verified_only,
        )
        case_filters = request.filters.model_dump(exclude_none=True)
        if request.context.trace_id:
            case_filters["exclude_session_id"] = request.context.session_id
        case_result = await retrieval_service.search(
            SourceType.CASE,
            request.query,
            case_filters,
            trace_id=request.context.trace_id,
            mode=mode,
            top_k=request.top_k,
            score_threshold=request.score_threshold,
        )
        metadata = ticket_result.retrieval_metadata
        combined = ticket_result.model_dump(mode="json")
        combined["ranked_evidence"] = [
            *ticket_result.model_dump(mode="json")["ranked_evidence"],
            *case_result.model_dump(mode="json")["ranked_evidence"],
        ][: request.top_k]
        degraded = sorted(
            set(metadata.degraded_components + case_result.retrieval_metadata.degraded_components)
        )
        return _result(
            request.context.trace_id,
            combined,
            source_system="retrieval",
            partial=metadata.partial_result or case_result.retrieval_metadata.partial_result,
            warnings=degraded,
            retrieval_mode=metadata.retrieval_mode,
        )

    registry.register("get_device_profile", DeviceProfileInput, device)
    registry.register("get_alarm_detail", AlarmDetailInput, alarm)
    registry.register("query_timeseries_window", TimeseriesWindowInput, timeseries)
    registry.register("search_manual_chunks", ManualSearchInput, manual)
    registry.register("search_similar_tickets", TicketSearchInput, tickets)
    return registry
