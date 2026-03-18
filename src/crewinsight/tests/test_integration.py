"""
Real integration tests — no mocks.

Requires FINNHUB_API_KEY in the environment. Azure Search is skipped
(empty endpoint) so the crew relies entirely on live Finnhub data.

Run:
    AZURE_OPENAI_ENDPOINT=x AZURE_OPENAI_API_KEY=x \
    AZURE_SEARCH_ENDPOINT=  AZURE_SEARCH_API_KEY=  \
    FINNHUB_API_KEY=<key> \
    uv run pytest src/crewinsight/tests/test_integration.py -v
"""
from __future__ import annotations

import asyncio
import os

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# ---------------------------------------------------------------------------
# Skip entire module if Finnhub key is absent
# ---------------------------------------------------------------------------
FINNHUB_KEY = os.getenv("FINNHUB_API_KEY", "")
pytestmark = pytest.mark.skipif(
    not FINNHUB_KEY,
    reason="FINNHUB_API_KEY not set — skipping integration tests",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
async def _wait_for_complete(client: AsyncClient, run_id: str, timeout: float = 30.0) -> dict:
    """Poll /status until complete or failed, then return the status payload."""
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        r = await client.get(f"/api/v1/status/{run_id}")
        assert r.status_code == 200
        data = r.json()
        if data["status"] in ("complete", "failed"):
            return data
        await asyncio.sleep(1)
    pytest.fail(f"run {run_id} did not finish within {timeout}s")


# ---------------------------------------------------------------------------
# Finnhub direct tests (no FastAPI, raw HTTP)
# ---------------------------------------------------------------------------
class TestFinnhubDirect:
    """Verify Finnhub is reachable and returns real data before testing the crew."""

    @pytest.mark.asyncio
    async def test_symbol_search_salesforce(self):
        from crewinsight.data_sources.finnhub import FinnhubClient
        client = FinnhubClient(api_key=FINNHUB_KEY)
        symbol = await client.search_symbol("Salesforce")
        assert symbol == "CRM", f"Expected CRM, got {symbol!r}"

    @pytest.mark.asyncio
    async def test_company_profile_crm(self):
        from crewinsight.data_sources.finnhub import FinnhubClient
        client = FinnhubClient(api_key=FINNHUB_KEY)
        profile = await client.company_profile("CRM")
        assert profile.get("name"), "Profile should have a name"
        assert profile.get("marketCapitalization", 0) > 0, "Market cap should be positive"
        assert profile.get("ticker") == "CRM"

    @pytest.mark.asyncio
    async def test_peers_crm(self):
        from crewinsight.data_sources.finnhub import FinnhubClient
        client = FinnhubClient(api_key=FINNHUB_KEY)
        peers = await client.company_peers("CRM")
        assert len(peers) >= 3, f"Expected at least 3 peers, got {peers}"
        assert "CRM" not in peers, "Peers should not include the company itself"

    @pytest.mark.asyncio
    async def test_company_news_crm(self):
        from crewinsight.data_sources.finnhub import FinnhubClient
        client = FinnhubClient(api_key=FINNHUB_KEY)
        news = await client.company_news("CRM")
        assert len(news) > 0, "Expected at least one news article"
        first = news[0]
        assert first.get("headline"), "News article must have a headline"

    @pytest.mark.asyncio
    async def test_peer_details_returns_profile_and_news(self):
        from crewinsight.data_sources.finnhub import FinnhubClient
        client = FinnhubClient(api_key=FINNHUB_KEY)
        profile, news = await client.peer_details("ADBE")
        assert profile.get("name") == "Adobe Inc"
        assert isinstance(news, list)


# ---------------------------------------------------------------------------
# ResearchToolset integration (Finnhub path, no Azure Search)
# ---------------------------------------------------------------------------
class TestResearchToolset:

    @pytest.mark.asyncio
    async def test_research_summary_returns_facts_and_competitors(self):
        from crewinsight.azure_clients import AzureSearchRAG
        from crewinsight.crew.tools import ResearchToolset
        from crewinsight.data_sources.finnhub import FinnhubClient

        # Azure Search with empty endpoint → client=None, returns []
        rag = AzureSearchRAG(endpoint="", api_key="", index_name="")
        finnhub = FinnhubClient(api_key=FINNHUB_KEY)
        toolset = ResearchToolset(rag, finnhub_client=finnhub)

        result = await toolset.research_summary("Salesforce", "CRM")

        assert isinstance(result["facts"], list)
        assert len(result["facts"]) > 0, "Expected facts from Finnhub news"
        assert result["symbol"] == "CRM"
        assert len(result["peers"]) >= 3
        assert len(result["peer_details"]) >= 3

        # Peer details should have real company names
        for sym, (profile, news) in result["peer_details"].items():
            assert profile.get("name"), f"Peer {sym} has no name in profile"


# ---------------------------------------------------------------------------
# Full API pipeline: POST /research → poll /status → GET /report
# ---------------------------------------------------------------------------
class TestAPIEndToEnd:

    @pytest_asyncio.fixture
    async def api_client(self):
        """ASGI test client wired to a fresh app instance with real Finnhub."""
        import importlib
        import crewinsight.api.routes as routes_mod

        # Reload routes module so it picks up the current env vars (Finnhub key)
        importlib.reload(routes_mod)

        from crewinsight.api.main import app
        app.include_router(routes_mod.router, prefix="", tags=[])  # already included; harmless dup
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            yield c

    @pytest.mark.asyncio
    async def test_salesforce_crm_full_pipeline(self):
        """
        Launch a real research run for Salesforce/CRM and assert:
        - run starts and returns a run_id
        - status progresses to complete
        - report contains real competitors, SWOT items, and recommendations
        """
        from crewinsight.api.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # 1. Launch
            r = await client.post(
                "/api/v1/research",
                json={"company": "Salesforce", "segment": "CRM"},
            )
            assert r.status_code == 200, r.text
            run_id = r.json()["run_id"]
            assert run_id

            # 2. Poll to completion
            final_status = await _wait_for_complete(client, run_id, timeout=30.0)
            assert final_status["status"] == "complete", (
                f"Run failed: {final_status.get('error')}"
            )

            # 3. Fetch report
            r = await client.get(f"/api/v1/report/{run_id}")
            assert r.status_code == 200
            report = r.json()

            # Executive summary mentions the company
            assert "Salesforce" in report["executive_summary"]

            # Real competitors from Finnhub
            assert len(report["competitors"]) >= 3, (
                f"Expected >=3 competitors, got {len(report['competitors'])}"
            )
            for comp in report["competitors"]:
                assert comp["name"], "Competitor must have a name"
                assert comp["overview"], "Competitor must have an overview"
                assert comp["pricing"].startswith("Market cap:"), (
                    f"Unexpected pricing format: {comp['pricing']!r}"
                )
                assert len(comp["news_highlights"]) > 0, (
                    f"Competitor {comp['name']} has no news highlights"
                )

            # SWOT populated from real facts
            swot = report["swot"]
            total_swot_items = sum(len(v) for v in swot.values())
            assert total_swot_items > 0, "SWOT should have at least one item"

            # At least one recommendation
            assert len(report["recommendations"]) > 0

            # All 4 agents ran
            assert report["metadata"]["total_agents"] == 4
            assert report["metadata"]["duration_seconds"] > 0
            assert len(report["agent_outputs"]) == 4

    @pytest.mark.asyncio
    async def test_invalid_run_id_returns_404(self):
        from crewinsight.api.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.get("/api/v1/report/does-not-exist")
            assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_missing_fields_rejected(self):
        from crewinsight.api.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.post("/api/v1/research", json={"company": "Salesforce"})
            assert r.status_code == 422  # missing segment
