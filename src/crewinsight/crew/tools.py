from __future__ import annotations

import asyncio
import json
from typing import Any, List

from openai import AsyncAzureOpenAI

from crewinsight.azure_clients import AzureSearchRAG
from crewinsight.config import settings
from crewinsight.data_sources.finnhub import FinnhubClient

# GPT-4o deployment name on the Azure OpenAI resource
_DEPLOYMENT = "gpt-4o"
# Cap facts sent to GPT to limit token spend per call
_MAX_FACTS = 30


def _openai_client() -> AsyncAzureOpenAI:
    return AsyncAzureOpenAI(
        azure_endpoint=settings.azure_openai_endpoint,
        api_key=settings.azure_openai_api_key,
        api_version="2024-02-01",
    )


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

        # Build facts list for AnalystAgent / StrategistAgent
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
    """Uses GPT-4o (Azure OpenAI) to extract real SWOT and strategic recommendations."""

    async def extract_swot(self, facts: List[str]) -> tuple[dict, tuple[int, int]]:
        """Returns (swot_dict, (input_tokens, output_tokens))."""
        facts_text = "\n".join(f"- {f}" for f in facts[:_MAX_FACTS])

        prompt = f"""You are a competitive intelligence analyst. Given the following market research facts, extract a concise SWOT analysis.

FACTS:
{facts_text}

Return a JSON object with exactly these keys: strengths, weaknesses, opportunities, threats.
Each key maps to a list of 2-4 short, specific, actionable strings grounded in the facts above.
Return only valid JSON, no markdown fences."""

        client = _openai_client()
        response = await client.chat.completions.create(
            model=_DEPLOYMENT,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=600,
        )
        usage = (response.usage.prompt_tokens, response.usage.completion_tokens)
        raw = response.choices[0].message.content or ""
        try:
            result = json.loads(raw)
            for key in ("strengths", "weaknesses", "opportunities", "threats"):
                if key not in result:
                    result[key] = []
            return result, usage
        except json.JSONDecodeError:
            return {"strengths": [], "weaknesses": [], "opportunities": [], "threats": []}, usage

    async def format_recommendations(self, facts: List[str]) -> tuple[List[dict], tuple[int, int]]:
        """Returns (recommendations_list, (input_tokens, output_tokens))."""
        facts_text = "\n".join(f"- {f}" for f in facts[:_MAX_FACTS])

        prompt = f"""You are a strategic business advisor. Given the following market research facts, generate 3 specific, actionable strategic recommendations.

FACTS:
{facts_text}

Return a JSON array of exactly 3 objects, each with:
- "title": short action-oriented title (max 8 words)
- "rationale": 1-2 sentence explanation grounded in the facts above
- "expected_impact": concrete business outcome if acted on

Return only valid JSON array, no markdown fences."""

        client = _openai_client()
        response = await client.chat.completions.create(
            model=_DEPLOYMENT,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.4,
            max_tokens=700,
        )
        usage = (response.usage.prompt_tokens, response.usage.completion_tokens)
        raw = response.choices[0].message.content or ""
        try:
            recs = json.loads(raw)
            return (recs[:3] if isinstance(recs, list) else []), usage
        except json.JSONDecodeError:
            return [], usage
