from __future__ import annotations

import datetime
import hashlib
import logging

from fastapi import HTTPException, Request

from .store import AzureTableStore

logger = logging.getLogger(__name__)


def _ip_from_request(request: Request) -> str:
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _hash_ip(ip: str) -> str:
    return hashlib.sha256(ip.encode()).hexdigest()[:16]


def _current_hour_utc() -> str:
    now = datetime.datetime.now(datetime.timezone.utc)
    return now.strftime("%Y%m%d%H")


def _current_date_utc() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d")


class TableRateLimiter:
    """Azure Table Storage-backed rate limiter.

    Enforces two independent limits on POST /api/v1/research:
      - Per-IP:      N requests per hour (sliding fixed window = top-of-hour reset)
      - Global daily: M requests per UTC day across all users/replicas

    When Table Storage is unavailable (store.client is None or a transient
    error occurs), both checks pass through — permissive degradation keeps
    the API available at the cost of temporarily unenforced limits.
    """

    def __init__(
        self,
        store: AzureTableStore,
        per_ip_limit: int,
        global_daily_limit: int,
    ) -> None:
        self._store = store
        self._per_ip_limit = per_ip_limit
        self._global_daily_limit = global_daily_limit

    async def check_ip(self, request: Request) -> None:
        ip = _ip_from_request(request)
        ip_hash = _hash_ip(ip)
        row_key = f"ip:{ip_hash}:{_current_hour_utc()}"
        try:
            count = await self._store.increment(row_key, self._per_ip_limit)
        except ValueError as exc:
            current = int(str(exc))
            logger.info("rate_limit: per-IP limit hit for %s (count=%d)", ip_hash, current)
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded: {self._per_ip_limit} requests per hour per IP.",
            )
        if count == -1:
            logger.warning("rate_limit: Table Storage unavailable, passing through per-IP check")

    async def check_global(self) -> None:
        row_key = f"global:{_current_date_utc()}"
        try:
            count = await self._store.increment(row_key, self._global_daily_limit)
        except ValueError as exc:
            current = int(str(exc))
            logger.info("rate_limit: global daily limit hit (count=%d)", current)
            raise HTTPException(
                status_code=429,
                detail=f"Daily request limit of {self._global_daily_limit} reached. Try again tomorrow.",
            )
        if count == -1:
            logger.warning("rate_limit: Table Storage unavailable, passing through global check")
