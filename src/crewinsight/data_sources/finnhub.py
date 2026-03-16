from __future__ import annotations

import asyncio
from datetime import date, timedelta
from typing import Any

import httpx


class FinnhubClient:
    BASE = "https://finnhub.io/api/v1"

    def __init__(self, api_key: str):
        self._api_key = api_key

    def _params(self, **kwargs: Any) -> dict[str, Any]:
        return {"token": self._api_key, **kwargs}

    async def search_symbol(self, company: str) -> str | None:
        """Return the best-matching ticker for a company name."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.get(f"{self.BASE}/search", params=self._params(q=company))
                r.raise_for_status()
                results = r.json().get("result", [])
                # Prefer exact common stock matches
                for item in results:
                    if item.get("type") == "Common Stock":
                        return item["symbol"]
                return results[0]["symbol"] if results else None
        except Exception:
            return None

    async def company_profile(self, symbol: str) -> dict[str, Any]:
        """Return company profile from Finnhub /stock/profile2."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.get(f"{self.BASE}/stock/profile2", params=self._params(symbol=symbol))
                r.raise_for_status()
                return r.json()
        except Exception:
            return {}

    async def company_peers(self, symbol: str) -> list[str]:
        """Return list of peer tickers."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.get(f"{self.BASE}/stock/peers", params=self._params(symbol=symbol))
                r.raise_for_status()
                peers = r.json()
                # Exclude the symbol itself
                return [p for p in peers if p != symbol]
        except Exception:
            return []

    async def company_news(self, symbol: str, days: int = 30) -> list[dict[str, Any]]:
        """Return recent company news articles."""
        try:
            to_date = date.today()
            from_date = to_date - timedelta(days=days)
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.get(
                    f"{self.BASE}/company-news",
                    params=self._params(
                        symbol=symbol,
                        **{"from": from_date.isoformat(), "to": to_date.isoformat()},
                    ),
                )
                r.raise_for_status()
                return r.json() or []
        except Exception:
            return []

    async def basic_financials(self, symbol: str) -> dict[str, Any]:
        """Return key financial metrics."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.get(f"{self.BASE}/stock/metric", params=self._params(symbol=symbol, metric="all"))
                r.raise_for_status()
                return r.json().get("metric", {})
        except Exception:
            return {}

    async def peer_details(self, peer_symbol: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        """Fetch profile and news for a peer concurrently."""
        profile, news = await asyncio.gather(
            self.company_profile(peer_symbol),
            self.company_news(peer_symbol),
        )
        return profile, news
