"""
Unit tests for rate limiting — AzureTableStore logic and TableRateLimiter.

No Azure credentials required. An in-memory fake replaces AzureTableStore so
every test is fast and deterministic.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException
from starlette.requests import Request
from starlette.datastructures import Headers

from crewinsight.rate_limit.limiter import TableRateLimiter


# ---------------------------------------------------------------------------
# In-memory fake store — mirrors AzureTableStore.increment / get_count contract
# ---------------------------------------------------------------------------

class FakeStore:
    """Pure in-memory replacement for AzureTableStore."""

    def __init__(self, unavailable: bool = False) -> None:
        self._counts: dict[str, int] = {}
        self._unavailable = unavailable
        # Expose a non-None client so TableRateLimiter never short-circuits
        self.client = object() if not unavailable else None

    async def increment(self, row_key: str, limit: int) -> int:
        if self._unavailable:
            return -1
        current = self._counts.get(row_key, 0)
        if current >= limit:
            raise ValueError(current)
        self._counts[row_key] = current + 1
        return current + 1

    async def get_count(self, row_key: str) -> int | None:
        if self._unavailable:
            return None
        return self._counts.get(row_key, 0)


# ---------------------------------------------------------------------------
# Request builder helpers
# ---------------------------------------------------------------------------

def _make_request(ip: str = "1.2.3.4", forwarded_for: str | None = None) -> Request:
    """Build a minimal Starlette Request with just enough for _ip_from_request."""
    headers: dict[str, str] = {}
    if forwarded_for:
        headers["x-forwarded-for"] = forwarded_for
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/research",
        "query_string": b"",
        "headers": Headers(headers=headers).raw,
        "client": (ip, 12345),
    }
    return Request(scope)


# ---------------------------------------------------------------------------
# AzureTableStore.increment contract (via FakeStore)
# ---------------------------------------------------------------------------

class TestFakeStoreIncrement:

    @pytest.mark.asyncio
    async def test_first_increment_returns_one(self):
        store = FakeStore()
        count = await store.increment("k", limit=5)
        assert count == 1

    @pytest.mark.asyncio
    async def test_counter_increments_sequentially(self):
        store = FakeStore()
        for expected in range(1, 6):
            count = await store.increment("k", limit=10)
            assert count == expected

    @pytest.mark.asyncio
    async def test_raises_value_error_at_limit(self):
        store = FakeStore()
        for _ in range(3):
            await store.increment("k", limit=3)
        with pytest.raises(ValueError) as exc_info:
            await store.increment("k", limit=3)
        assert int(str(exc_info.value)) == 3

    @pytest.mark.asyncio
    async def test_raises_value_error_above_limit(self):
        store = FakeStore()
        # Pre-load the counter above the limit
        store._counts["k"] = 10
        with pytest.raises(ValueError) as exc_info:
            await store.increment("k", limit=5)
        assert int(str(exc_info.value)) == 10

    @pytest.mark.asyncio
    async def test_unavailable_returns_minus_one(self):
        store = FakeStore(unavailable=True)
        result = await store.increment("k", limit=3)
        assert result == -1

    @pytest.mark.asyncio
    async def test_independent_row_keys_do_not_interfere(self):
        store = FakeStore()
        await store.increment("a", limit=2)
        await store.increment("b", limit=2)
        count_a = await store.increment("a", limit=10)
        assert count_a == 2
        count_b = await store.increment("b", limit=10)
        assert count_b == 2


# ---------------------------------------------------------------------------
# TableRateLimiter.check_ip
# ---------------------------------------------------------------------------

class TestCheckIP:

    @pytest.mark.asyncio
    async def test_allows_requests_under_limit(self):
        store = FakeStore()
        limiter = TableRateLimiter(store, per_ip_limit=5, global_daily_limit=100)
        req = _make_request(ip="10.0.0.1")
        for _ in range(5):
            await limiter.check_ip(req)  # must not raise

    @pytest.mark.asyncio
    async def test_blocks_on_limit_exceeded(self):
        store = FakeStore()
        limiter = TableRateLimiter(store, per_ip_limit=3, global_daily_limit=100)
        req = _make_request(ip="10.0.0.1")
        for _ in range(3):
            await limiter.check_ip(req)
        with pytest.raises(HTTPException) as exc_info:
            await limiter.check_ip(req)
        assert exc_info.value.status_code == 429
        assert "3 requests per hour" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_different_ips_have_independent_counters(self):
        store = FakeStore()
        limiter = TableRateLimiter(store, per_ip_limit=2, global_daily_limit=100)
        req_a = _make_request(ip="1.1.1.1")
        req_b = _make_request(ip="2.2.2.2")
        await limiter.check_ip(req_a)
        await limiter.check_ip(req_a)  # hits limit for IP A
        # IP B should still be allowed
        await limiter.check_ip(req_b)
        await limiter.check_ip(req_b)

    @pytest.mark.asyncio
    async def test_x_forwarded_for_used_when_present(self):
        store = FakeStore()
        limiter = TableRateLimiter(store, per_ip_limit=1, global_daily_limit=100)
        # X-Forwarded-For takes precedence over client IP
        req = _make_request(ip="10.0.0.1", forwarded_for="5.6.7.8")
        await limiter.check_ip(req)  # count = 1 for 5.6.7.8
        with pytest.raises(HTTPException) as exc_info:
            await limiter.check_ip(req)  # count = 2, limit = 1
        assert exc_info.value.status_code == 429

    @pytest.mark.asyncio
    async def test_passes_through_when_store_unavailable(self):
        store = FakeStore(unavailable=True)
        limiter = TableRateLimiter(store, per_ip_limit=1, global_daily_limit=100)
        req = _make_request(ip="10.0.0.1")
        # Even after "many" requests, no 429 when store is down
        for _ in range(10):
            await limiter.check_ip(req)


# ---------------------------------------------------------------------------
# TableRateLimiter.check_global
# ---------------------------------------------------------------------------

class TestCheckGlobal:

    @pytest.mark.asyncio
    async def test_allows_requests_under_daily_limit(self):
        store = FakeStore()
        limiter = TableRateLimiter(store, per_ip_limit=100, global_daily_limit=5)
        for _ in range(5):
            await limiter.check_global()  # must not raise

    @pytest.mark.asyncio
    async def test_blocks_when_daily_limit_reached(self):
        store = FakeStore()
        limiter = TableRateLimiter(store, per_ip_limit=100, global_daily_limit=3)
        for _ in range(3):
            await limiter.check_global()
        with pytest.raises(HTTPException) as exc_info:
            await limiter.check_global()
        assert exc_info.value.status_code == 429
        assert "3" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_global_counter_is_shared_across_ips(self):
        store = FakeStore()
        limiter = TableRateLimiter(store, per_ip_limit=100, global_daily_limit=2)
        req_a = _make_request(ip="1.1.1.1")
        req_b = _make_request(ip="2.2.2.2")

        # One request each — together they exhaust the global limit
        await limiter.check_ip(req_a)
        await limiter.check_global()

        await limiter.check_ip(req_b)
        await limiter.check_global()

        # Third request: global limit hit regardless of which IP
        with pytest.raises(HTTPException) as exc_info:
            await limiter.check_global()
        assert exc_info.value.status_code == 429

    @pytest.mark.asyncio
    async def test_passes_through_when_store_unavailable(self):
        store = FakeStore(unavailable=True)
        limiter = TableRateLimiter(store, per_ip_limit=100, global_daily_limit=1)
        for _ in range(10):
            await limiter.check_global()  # must not raise


# ---------------------------------------------------------------------------
# Row-key namespacing — ip and global counters must not collide
# ---------------------------------------------------------------------------

class TestRowKeyIsolation:

    @pytest.mark.asyncio
    async def test_ip_and_global_keys_are_distinct(self):
        store = FakeStore()
        limiter = TableRateLimiter(store, per_ip_limit=2, global_daily_limit=2)
        req = _make_request(ip="3.3.3.3")

        await limiter.check_ip(req)
        await limiter.check_ip(req)  # exhausts ip limit

        # Global should still have room — different row key
        await limiter.check_global()
        await limiter.check_global()

        # Confirm both row keys are present and distinct
        assert len(store._counts) == 2
        keys = list(store._counts.keys())
        assert any(k.startswith("ip:") for k in keys)
        assert any(k.startswith("global:") for k in keys)

    @pytest.mark.asyncio
    async def test_get_count_returns_zero_for_unknown_key(self):
        store = FakeStore()
        assert await store.get_count("nonexistent") == 0

    @pytest.mark.asyncio
    async def test_get_count_matches_increment_count(self):
        store = FakeStore()
        for _ in range(4):
            await store.increment("mykey", limit=10)
        assert await store.get_count("mykey") == 4
