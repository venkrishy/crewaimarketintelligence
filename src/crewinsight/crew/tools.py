from __future__ import annotations

import asyncio
from typing import Any, List

from crewinsight.azure_clients import AzureSearchRAG
from crewinsight.data_sources.finnhub import FinnhubClient


class ResearchToolset:
    def __init__(self, search_rag: AzureSearchRAG, finnhub_client: FinnhubClient | None = None):
        self.search = search_rag
        self.finnhub = finnhub_client

    async def search_documents(self, query: str, top_k: int = 5) -> List[str]:
        return await self.search.query(query, top_k)

    async def research_summary(self, company: str, segment: str) -> dict[str, Any]:
        """Return structured research data: facts list + Finnhub data."""
        rag_facts: List[str] = await self.search_documents(f"{company} {segment}")

        if not self.finnhub or not self.finnhub._api_key:
            return {"facts": rag_facts, "symbol": None, "profile": {}, "peers": [], "peer_details": {}, "financials": {}}

        # Resolve ticker
        symbol = await self.finnhub.search_symbol(company)
        if not symbol:
            return {"facts": rag_facts, "symbol": None, "profile": {}, "peers": [], "peer_details": {}, "financials": {}}

        # Fetch main company data concurrently
        profile, peers, financials = await asyncio.gather(
            self.finnhub.company_profile(symbol),
            self.finnhub.company_peers(symbol),
            self.finnhub.basic_financials(symbol),
        )

        # Fetch news for main company and up to 5 peers concurrently
        capped_peers = peers[:5]
        main_news_task = self.finnhub.company_news(symbol)
        peer_tasks = [self.finnhub.peer_details(p) for p in capped_peers]
        all_results = await asyncio.gather(main_news_task, *peer_tasks)
        main_news: list[dict] = all_results[0]
        peer_details: dict[str, tuple] = {
            capped_peers[i]: all_results[i + 1] for i in range(len(capped_peers))
        }

        # Build facts list for backward compat with AnalystAgent / StrategistAgent
        facts: List[str] = list(rag_facts)
        if profile.get("description"):
            facts.append(profile["description"])
        for article in main_news[:5]:
            headline = article.get("headline", "")
            if headline:
                facts.append(headline)
        for peer_sym, (p_profile, p_news) in peer_details.items():
            name = p_profile.get("name", peer_sym)
            industry = p_profile.get("finnhubIndustry", "")
            if name:
                facts.append(f"Competitor {name} operates in {industry}." if industry else f"Competitor: {name}")
            for article in p_news[:2]:
                headline = article.get("headline", "")
                if headline:
                    facts.append(headline)

        return {
            "facts": facts,
            "symbol": symbol,
            "profile": profile,
            "peers": capped_peers,
            "peer_details": peer_details,
            "main_news": main_news,
            "financials": financials,
        }


class FormatterTool:
    async def extract_swot(self, facts: List[str]) -> dict:
        await asyncio.sleep(0)
        return {
            "strengths": [f for f in facts[:2]],
            "weaknesses": [f for f in facts[2:4]],
            "opportunities": [f for f in facts[4:6]],
            "threats": [f for f in facts[6:8]],
        }

    async def format_recommendations(self, facts: List[str]) -> List[dict]:
        await asyncio.sleep(0)
        recs = []
        for i in range(0, min(len(facts), 6), 2):
            recs.append({
                "title": f"Recommendation {i//2 + 1}",
                "rationale": facts[i],
                "expected_impact": facts[i + 1] if i + 1 < len(facts) else "TBD",
            })
        return recs
