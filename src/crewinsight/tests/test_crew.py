import pytest
from crewinsight.crew.process import CrewCoordinator
from crewinsight.crew.tools import ResearchToolset, FormatterTool
from crewinsight.telemetry import CrewMetrics

class DummyResearchTool(ResearchToolset):
    def __init__(self):
        pass
    async def research_summary(self, company: str, segment: str):
        return ["fact1", "fact2"]

class DummyFormatter(FormatterTool):
    async def extract_swot(self, facts):
        return {"strengths": [], "weaknesses": [], "opportunities": [], "threats": []}
    async def format_recommendations(self, facts):
        return [{"title": "Rec", "rationale": "Rat", "expected_impact": "Imp"}]

@pytest.mark.asyncio
async def test_crew_coordinator():
    metrics = CrewMetrics()
    tools = DummyResearchTool()
    formatter = DummyFormatter()
    coordinator = CrewCoordinator(tools, formatter, metrics)
    
    report = await coordinator.run("test-run", "TestCo", "Segment")
    assert report.metadata.run_id == "test-run"
    assert report.metadata.cost_usd > 0
    assert report.metadata.duration_seconds > 0
