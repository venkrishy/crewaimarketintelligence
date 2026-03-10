from __future__ import annotations

import asyncio
from typing import List

import httpx
from bs4 import BeautifulSoup

from crewinsight.azure_clients import AzureSearchRAG


class ResearchToolset:
    def __init__(self, search_rag: AzureSearchRAG):
        self.search = search_rag

    async def search_documents(self, query: str, top_k: int = 5) -> List[str]:
        return await self.search.query(query, top_k)

    async def scrape_news(self, url: str) -> List[str]:
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(url)
                response.raise_for_status()
                soup = BeautifulSoup(response.text, "html.parser")
                return [p.get_text(strip=True) for p in soup.select("p") if p.get_text(strip=True)]
        except httpx.HTTPError:
            return []

    async def research_summary(self, company: str, segment: str) -> List[str]:
        results = await self.search_documents(f"{company} {segment}")
        news = await self.scrape_news("https://www.bloomberg.com")
        return results + news[:3] if results else news[:3]


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
