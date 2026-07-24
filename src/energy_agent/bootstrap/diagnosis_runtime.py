from dataclasses import dataclass
from typing import cast

from energy_agent.agent.events import DiagnosisEventEmitter
from energy_agent.agent.ports import (
    DiagnosisGraphPort,
    MemoryWriterPort,
    StepLogPort,
    ToolLogPort,
)
from energy_agent.agent.workflow import build_diagnosis_graph
from energy_agent.model.gateway import ModelGateway
from energy_agent.observability.tracing import Tracer
from energy_agent.reliability.registry import CircuitBreakerRegistry
from energy_agent.tools.executor import ToolExecutor
from energy_agent.tools.registry import ToolRegistry


@dataclass(frozen=True, slots=True)
class DefaultDiagnosisRuntimeFactory:
    tools: ToolRegistry
    tracer: Tracer
    model: ModelGateway | None
    circuit_breakers: CircuitBreakerRegistry | None

    def create(
        self,
        *,
        tool_logger: ToolLogPort,
        memory_writer: MemoryWriterPort,
        step_logger: StepLogPort,
        emitter: DiagnosisEventEmitter,
    ) -> DiagnosisGraphPort:
        executor = ToolExecutor(
            self.tools,
            self.tracer,
            tool_logger=tool_logger,
            circuit_breakers=self.circuit_breakers,
        )
        return cast(
            DiagnosisGraphPort,
            build_diagnosis_graph(
                executor,
                self.tracer,
                memory_writer=memory_writer,
                step_logger=step_logger,
                model_gateway=self.model,
                event_emitter=emitter,
            ),
        )
