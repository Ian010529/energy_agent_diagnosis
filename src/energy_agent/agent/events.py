import asyncio
from collections.abc import AsyncIterator
from datetime import datetime
from time import monotonic

from energy_agent.agent.state import DiagnosisState
from energy_agent.contracts.events import SSEEvent, SSEEventType
from energy_agent.core.time import utc_now


class DiagnosisEventEmitter:
    first_event_latency_seconds: float | None = None

    async def emit(self, event: SSEEventType, state: DiagnosisState, **payload: object) -> None:
        raise NotImplementedError


class NoopDiagnosisEventEmitter(DiagnosisEventEmitter):
    async def emit(self, event: SSEEventType, state: DiagnosisState, **payload: object) -> None:
        return None


class QueueDiagnosisEventEmitter(DiagnosisEventEmitter):
    def __init__(self) -> None:
        self._queue: asyncio.Queue[SSEEvent | None] = asyncio.Queue()
        self._sequence = 0
        self._closed = False
        self._started = monotonic()
        self.first_event_at: datetime | None = None

    async def emit(self, event: SSEEventType, state: DiagnosisState, **payload: object) -> None:
        if self._closed:
            return
        if self.first_event_latency_seconds is None:
            self.first_event_latency_seconds = monotonic() - self._started
            self.first_event_at = utc_now()
        self._sequence += 1
        await self._queue.put(
            SSEEvent(
                event=event,
                event_sequence=self._sequence,
                timestamp=utc_now(),
                session_id=state.session_id,
                run_id=state.run_id,
                trace_id=state.trace_id,
                phase=state.phase,
                payload=payload,
            )
        )

    async def close(self) -> None:
        if not self._closed:
            self._closed = True
            await self._queue.put(None)

    async def events(self) -> AsyncIterator[SSEEvent]:
        while True:
            item = await self._queue.get()
            if item is None:
                return
            yield item
