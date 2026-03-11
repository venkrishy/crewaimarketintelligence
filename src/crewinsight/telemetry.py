from __future__ import annotations

from dataclasses import dataclass, field
from statistics import mean
from typing import Dict, List

from opentelemetry import trace
from azure.monitor.opentelemetry.exporter import AzureMonitorTraceExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor


def setup_telemetry(service_name: str) -> None:
    import os
    provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
    conn_str = os.environ.get("APPLICATIONINSIGHTS_CONNECTION_STRING")
    if conn_str:
        exporter = AzureMonitorTraceExporter(connection_string=conn_str)
        processor = BatchSpanProcessor(exporter)
        provider.add_span_processor(processor)
    trace.set_tracer_provider(provider)


@dataclass
class CrewMetrics:
    costs: List[float] = field(default_factory=list)
    durations: List[float] = field(default_factory=list)
    agent_costs: Dict[str, List[float]] = field(default_factory=dict)

    def record(self, cost_usd: float, duration_seconds: float, agent_role: str) -> None:
        self.costs.append(cost_usd)
        self.durations.append(duration_seconds)
        self.agent_costs.setdefault(agent_role, []).append(cost_usd)

    def aggregate(self) -> Dict[str, float]:
        most_expensive_agent = ""
        max_avg = 0.0
        for agent, list_cost in self.agent_costs.items():
            avg = mean(list_cost)
            if avg > max_avg:
                most_expensive_agent = agent
                max_avg = avg
        return {
            "average_cost": mean(self.costs) if self.costs else 0.0,
            "average_duration": mean(self.durations) if self.durations else 0.0,
            "most_expensive_agent": most_expensive_agent,
        }
