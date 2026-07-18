from typing import Any, cast

from pydantic import BaseModel

from energy_agent.observability.tracing import Tracer
from energy_agent.providers.influxdb import InfluxTimeseriesProvider
from energy_agent.providers.mysql import MySQLDiagnosisProvider
from energy_agent.retrieval.keyword import rank_rows
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
) -> ToolResult:
    empty = data is None or data == [] or data == {}
    return ToolResult(
        success=not empty,
        status=ToolStatus.NOT_FOUND
        if empty
        else ToolStatus.PARTIAL_SUCCESS
        if partial
        else ToolStatus.OK,
        data=data,
        meta=ToolMeta(
            trace_id=trace_id,
            source_system=source_system,
            partial_result=partial,
            retrieval_mode="keyword_only" if partial else None,
        ),
        error_code="NOT_FOUND" if empty else "",
        error_message="No matching data" if empty else "",
        warnings=warnings or [],
    )


def build_registry(
    mysql: MySQLDiagnosisProvider,
    influx: InfluxTimeseriesProvider,
    tracer: Tracer | None = None,
) -> ToolRegistry:
    registry = ToolRegistry()

    async def device(payload: BaseModel) -> ToolResult:
        request = cast(DeviceProfileInput, payload)
        data = await mysql.get_device(request.device_id)
        return _result(request.context.trace_id, data, source_system="mysql")

    async def alarm(payload: BaseModel) -> ToolResult:
        request = cast(AlarmDetailInput, payload)
        data = await mysql.get_alarm(request.alarm_id, request.device_id)
        return _result(request.context.trace_id, data, source_system="mysql")

    async def timeseries(payload: BaseModel) -> ToolResult:
        request = cast(TimeseriesWindowInput, payload)
        data: dict[str, dict[str, Any]] = cast(
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
        manager = (
            tracer.start_span(
                "retrieval.keyword_search",
                trace_id=request.context.trace_id,
                metadata={"source": "manual", "filters": request.filters},
            )
            if tracer
            else None
        )
        if manager:
            with manager as span:
                rows = await mysql.manual_candidates(request.filters)
                ranked = rank_rows(
                    request.query,
                    rows,
                    ("alarm_name", "chapter_title", "summary_or_content"),
                    request.top_k,
                )
                span.set_output({"candidate_count": len(rows), "result_count": len(ranked)})
        else:
            rows = await mysql.manual_candidates(request.filters)
            ranked = rank_rows(
                request.query,
                rows,
                ("alarm_name", "chapter_title", "summary_or_content"),
                request.top_k,
            )
        return _result(
            request.context.trace_id,
            ranked,
            source_system="mysql",
            partial=True,
            warnings=["VECTOR_RETRIEVAL_NOT_ENABLED"],
        )

    async def tickets(payload: BaseModel) -> ToolResult:
        request = cast(TicketSearchInput, payload)
        manager = (
            tracer.start_span(
                "retrieval.keyword_search",
                trace_id=request.context.trace_id,
                metadata={
                    "source": "ticket",
                    "filters": request.filters,
                    "verified_only": request.verified_only,
                },
            )
            if tracer
            else None
        )
        if manager:
            with manager as span:
                rows = await mysql.ticket_candidates(
                    request.filters, verified_only=request.verified_only
                )
                ranked = rank_rows(
                    request.query,
                    rows,
                    ("alarm_name", "fault_symptom", "root_cause", "action_taken"),
                    request.top_k,
                )
                span.set_output({"candidate_count": len(rows), "result_count": len(ranked)})
        else:
            rows = await mysql.ticket_candidates(
                request.filters, verified_only=request.verified_only
            )
            ranked = rank_rows(
                request.query,
                rows,
                ("alarm_name", "fault_symptom", "root_cause", "action_taken"),
                request.top_k,
            )
        return _result(
            request.context.trace_id,
            ranked,
            source_system="mysql",
            partial=True,
            warnings=["VECTOR_RETRIEVAL_NOT_ENABLED"],
        )

    registry.register("get_device_profile", DeviceProfileInput, device)
    registry.register("get_alarm_detail", AlarmDetailInput, alarm)
    registry.register("query_timeseries_window", TimeseriesWindowInput, timeseries)
    registry.register("search_manual_chunks", ManualSearchInput, manual)
    registry.register("search_similar_tickets", TicketSearchInput, tickets)
    return registry
