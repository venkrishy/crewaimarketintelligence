from __future__ import annotations

import datetime
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

# GPT-4o pricing (Azure Standard tier, per token)
_COST_PER_INPUT_TOKEN = 2.50 / 1_000_000
_COST_PER_OUTPUT_TOKEN = 10.00 / 1_000_000


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
        research = await self.toolset.research_summary(company, segment)

        if isinstance(research, dict):
            facts: List[str] = research.get("facts", [])
            peer_details: Dict[str, Any] = research.get("peer_details", {})
        else:
            facts = list(research)
            peer_details = {}

        competitors: List[CompetitorProfile] = []

        for peer_sym, (p_profile, p_news) in peer_details.items():
            name = p_profile.get("name") or peer_sym
            overview = p_profile.get("description") or p_profile.get("finnhubIndustry", "")
            market_cap = p_profile.get("marketCapitalization")
            pricing = f"Market cap: ${market_cap:.0f}M" if market_cap else "N/A"
            key_products = [p_profile["weburl"]] if p_profile.get("weburl") else []
            headlines = [a["headline"] for a in p_news[:3] if a.get("headline")]
            competitors.append(
                CompetitorProfile(
                    name=name,
                    overview=overview,
                    key_products=key_products,
                    pricing=pricing,
                    news_highlights=headlines,
                )
            )

        if not competitors:
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
        # Research agent makes no LLM calls
        return {"facts": facts, "sources": facts[:3], "competitors": competitors, f"_output_{self.role}": agent_output, "_tokens_input": 0, "_tokens_output": 0}


class AnalystAgent(CrewAgent):
    def __init__(self, formatter: FormatterTool):
        super().__init__(role="Competitive Intelligence Analyst")
        self.formatter = formatter

    async def run(self, context: Dict[str, object]) -> Dict[str, object]:
        facts = context.get("facts", [])
        swot, usage = await self.formatter.extract_swot(facts)
        total_items = sum(len(v) for v in swot.values())
        agent_output = AgentOutput(
            role=self.role,
            summary=f"Extracted SWOT analysis with {total_items} total items across 4 quadrants.",
            data={k: v for k, v in swot.items()},
        )
        return {"swot": swot, f"_output_{self.role}": agent_output, "_tokens_input": usage[0], "_tokens_output": usage[1]}


class StrategistAgent(CrewAgent):
    def __init__(self, formatter: FormatterTool):
        super().__init__(role="Strategic Advisor")
        self.formatter = formatter

    async def run(self, context: Dict[str, object]) -> Dict[str, object]:
        facts = context.get("facts", [])
        recs, usage = await self.formatter.format_recommendations(facts)
        agent_output = AgentOutput(
            role=self.role,
            summary=f"Generated {len(recs)} strategic recommendations.",
            data={"recommendations": recs},
        )
        return {"recommendations": recs, f"_output_{self.role}": agent_output, "_tokens_input": usage[0], "_tokens_output": usage[1]}


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
            + ("Includes: " + ", ".join(summary_parts) + "." if summary_parts else "No data retrieved.")
        )

        writer_output = AgentOutput(
            role=self.role,
            summary=f"Assembled final report with {len(competitors)} competitors, {len(recs)} recommendations.",
            data={"executive_summary": executive_summary},
        )
        agent_outputs.append(writer_output)

        return {
            "report": CrewReport(
                executive_summary=executive_summary,
                company_overview={
                    "name": str(context["company"]),
                    "segment": str(context["segment"]),
                    "key_products": "",
                },
                competitors=competitors,
                swot=swot,
                recommendations=[Recommendation(**r) for r in recs],
                sources=sources,
                agent_outputs=agent_outputs,
                metadata=metadata,
            ),
            "_tokens_input": 0,
            "_tokens_output": 0,
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
        metadata = ReportMetadata(
            run_id=run_id,
            company=company,
            segment=segment,
            duration_seconds=0.0,
            total_tokens=0,
            cost_usd=0.0,
            created_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        )
        context: Dict[str, object] = {"company": company, "segment": segment, "metadata": metadata}
        agents = [
            self.research_agent,
            self.analyst_agent,
            self.strategist_agent,
            self.report_agent,
        ]
        report: CrewReport | None = None
        total_duration = 0.0
        total_input_tokens = 0
        total_output_tokens = 0

        for agent in agents:
            if on_agent_start:
                on_agent_start(agent.role)
            start = time.monotonic()
            result = await agent.run(context)
            duration = time.monotonic() - start
            total_duration += duration

            # Accumulate real token counts returned by each agent
            total_input_tokens += int(result.pop("_tokens_input", 0))
            total_output_tokens += int(result.pop("_tokens_output", 0))

            self.metrics.record(cost_usd=0.0, duration_seconds=duration, agent_role=agent.role)
            context.update(result)
            if agent is self.report_agent:
                report = result["report"]

        if not report:
            raise RuntimeError("Report agent failed to produce output")

        total_tokens = total_input_tokens + total_output_tokens
        cost_usd = (total_input_tokens * _COST_PER_INPUT_TOKEN) + (total_output_tokens * _COST_PER_OUTPUT_TOKEN)

        report.metadata.duration_seconds = total_duration
        report.metadata.total_tokens = total_tokens
        report.metadata.cost_usd = cost_usd
        return report
