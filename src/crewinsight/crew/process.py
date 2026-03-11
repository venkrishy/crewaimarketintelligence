from __future__ import annotations

import asyncio
import time
from typing import Dict

from crewinsight.crew.tools import FormatterTool, ResearchToolset
from crewinsight.models.report import (
    CompetitorProfile,
    CrewReport,
    Recommendation,
    ReportMetadata,
)
from crewinsight.telemetry import CrewMetrics


class CrewAgent:
    def __init__(self, role: str):
        self.role = role

    async def run(self, context: Dict[str, object]) -> Dict[str, object]:
        raise NotImplementedError


class ResearchAgent(CrewAgent):
    def __init__(self, toolset: ResearchToolset):
        super().__init__(role="Senior Market Researcher")
        self.toolset = toolset

    async def run(self, context: Dict[str, object]) -> Dict[str, object]:
        company = context["company"]
        segment = context["segment"]
        facts = await self.toolset.research_summary(company, segment)
        competitors = [
            CompetitorProfile(
                name=f"{company} Competitor {i+1}",
                overview=f"Auto-generated overview for competitor {i+1}",
                key_products=[f"Product {i+1}A", f"Product {i+1}B"],
                pricing="Tiered",
                news_highlights=facts[i : i + 2],
            )
            for i in range(min(3, len(facts)))
        ]
        return {"facts": facts, "sources": facts[:3], "competitors": competitors}


class AnalystAgent(CrewAgent):
    def __init__(self, formatter: FormatterTool):
        super().__init__(role="Competitive Intelligence Analyst")
        self.formatter = formatter

    async def run(self, context: Dict[str, object]) -> Dict[str, object]:
        facts = context.get("facts", [])
        swot = await self.formatter.extract_swot(facts)
        return {"swot": swot}


class StrategistAgent(CrewAgent):
    def __init__(self, formatter: FormatterTool):
        super().__init__(role="Strategic Advisor")
        self.formatter = formatter

    async def run(self, context: Dict[str, object]) -> Dict[str, object]:
        facts = context.get("facts", [])
        recs = await self.formatter.format_recommendations(facts)
        return {"recommendations": recs}


class ReportWriterAgent(CrewAgent):
    def __init__(self):
        super().__init__(role="Business Report Writer")

    async def run(self, context: Dict[str, object]) -> Dict[str, object]:
        metadata = context["metadata"]
        return {
            "report": CrewReport(
                executive_summary="Generated insights",
                company_overview={
                    "name": str(context["company"]),
                    "segment": str(context["segment"]),
                    "key_products": "Product A, Product B",
                },
                competitor_profiles=context.get("competitors", []),
                swot=context.get("swot", {}),
                strategic_recommendations=[
                    Recommendation(**r) for r in context.get("recommendations", [])
                ],
                sources=context.get("sources", []),
                metadata=metadata,
            )
        }


class CrewCoordinator:
    def __init__(self, research_tool: ResearchToolset, formatter: FormatterTool, metrics: CrewMetrics):
        self.metrics = metrics
        self.research_agent = ResearchAgent(research_tool)
        self.analyst_agent = AnalystAgent(formatter)
        self.strategist_agent = StrategistAgent(formatter)
        self.report_agent = ReportWriterAgent()

    async def run(self, run_id: str, company: str, segment: str) -> CrewReport:
        metadata = ReportMetadata(run_id=run_id, duration_seconds=0.0, total_tokens=0, cost_usd=0.0)
        context: Dict[str, object] = {"company": company, "segment": segment, "metadata": metadata}
        agents = [
            self.research_agent,
            self.analyst_agent,
            self.strategist_agent,
            self.report_agent,
        ]
        report: CrewReport | None = None
        per_run_costs: list[float] = []
        per_run_durations: list[float] = []
        for agent in agents:
            start = time.monotonic()
            result = await agent.run(context)
            duration = time.monotonic() - start
            cost = 0.1
            per_run_costs.append(cost)
            per_run_durations.append(duration)
            self.metrics.record(cost_usd=cost, duration_seconds=duration, agent_role=agent.role)
            context.update(result)
            if agent is self.report_agent:
                report = result["report"]
        if not report:
            raise RuntimeError("Report agent failed to produce output")
        metadata = report.metadata
        metadata.duration_seconds = sum(per_run_durations)
        metadata.cost_usd = sum(per_run_costs)
        metadata.total_tokens = int(metadata.duration_seconds * 10)
        return report
