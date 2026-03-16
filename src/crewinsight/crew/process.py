from __future__ import annotations

import asyncio
import time
from typing import Any, Callable, Dict, List, Optional

from crewinsight.crew.tools import FormatterTool, ResearchToolset
from crewinsight.models.report import (
    AgentOutput,
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
        agent_output = AgentOutput(
            role=self.role,
            summary=f"Gathered {len(facts)} research facts and identified {len(competitors)} competitors for {company} in {segment}.",
            data={"fact_count": len(facts), "competitor_count": len(competitors), "sample_facts": facts[:3]},
        )
        return {"facts": facts, "sources": facts[:3], "competitors": competitors, f"_output_{self.role}": agent_output}


class AnalystAgent(CrewAgent):
    def __init__(self, formatter: FormatterTool):
        super().__init__(role="Competitive Intelligence Analyst")
        self.formatter = formatter

    async def run(self, context: Dict[str, object]) -> Dict[str, object]:
        facts = context.get("facts", [])
        swot = await self.formatter.extract_swot(facts)
        total_items = sum(len(v) for v in swot.values())
        agent_output = AgentOutput(
            role=self.role,
            summary=f"Extracted SWOT analysis with {total_items} total items across 4 quadrants.",
            data={k: v for k, v in swot.items()},
        )
        return {"swot": swot, f"_output_{self.role}": agent_output}


class StrategistAgent(CrewAgent):
    def __init__(self, formatter: FormatterTool):
        super().__init__(role="Strategic Advisor")
        self.formatter = formatter

    async def run(self, context: Dict[str, object]) -> Dict[str, object]:
        facts = context.get("facts", [])
        recs = await self.formatter.format_recommendations(facts)
        agent_output = AgentOutput(
            role=self.role,
            summary=f"Generated {len(recs)} strategic recommendations.",
            data={"recommendations": recs},
        )
        return {"recommendations": recs, f"_output_{self.role}": agent_output}


class ReportWriterAgent(CrewAgent):
    def __init__(self):
        super().__init__(role="Business Report Writer")

    async def run(self, context: Dict[str, object]) -> Dict[str, object]:
        metadata = context["metadata"]
        agent_outputs: List[AgentOutput] = []
        for key, value in context.items():
            if key.startswith("_output_") and isinstance(value, AgentOutput):
                agent_outputs.append(value)

        competitors = context.get("competitors", [])
        swot = context.get("swot", {})
        recs = context.get("recommendations", [])
        sources = context.get("sources", [])

        summary_parts = []
        if competitors:
            summary_parts.append(f"{len(competitors)} competitor profiles")
        if swot:
            total_swot = sum(len(v) for v in swot.values())
            summary_parts.append(f"SWOT analysis ({total_swot} items)")
        if recs:
            summary_parts.append(f"{len(recs)} strategic recommendations")
        executive_summary = (
            f"Competitive intelligence report for {context['company']} in {context['segment']}. "
            + ("Includes: " + ", ".join(summary_parts) + "." if summary_parts else "No data retrieved — check Azure Search index and scraping configuration.")
        )

        writer_output = AgentOutput(
            role=self.role,
            summary=f"Assembled final report with {len(competitors)} competitors, {len(recs)} recommendations.",
            data={"sections": ["executive_summary", "competitors", "swot", "recommendations", "sources"]},
        )
        agent_outputs.append(writer_output)

        return {
            "report": CrewReport(
                executive_summary=executive_summary,
                company_overview={
                    "name": str(context["company"]),
                    "segment": str(context["segment"]),
                    "key_products": "Product A, Product B",
                },
                competitors=competitors,
                swot=swot,
                recommendations=[
                    Recommendation(**r) for r in recs
                ],
                sources=sources,
                agent_outputs=agent_outputs,
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

    async def run(
        self,
        run_id: str,
        company: str,
        segment: str,
        on_agent_start: Optional[Callable[[str], None]] = None,
    ) -> CrewReport:
        import datetime
        metadata = ReportMetadata(run_id=run_id, company=company, segment=segment, duration_seconds=0.0, total_tokens=0, cost_usd=0.0, created_at=datetime.datetime.utcnow().isoformat() + "Z")
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
            if on_agent_start:
                on_agent_start(agent.role)
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
