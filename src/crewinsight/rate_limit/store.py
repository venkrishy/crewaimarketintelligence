from __future__ import annotations

import asyncio
import logging
from typing import Optional

from azure.core.credentials import AzureKeyCredential
from azure.core.exceptions import HttpResponseError, ResourceNotFoundError
from azure.core.match_conditions import MatchConditions
from azure.data.tables.aio import TableServiceClient

logger = logging.getLogger(__name__)

_TABLE_NAME = "ratelimits"
_PARTITION_KEY = "rl"
_MAX_RETRIES = 3


class AzureTableStore:
    """Low-level Azure Table Storage wrapper.

    Follows the same conventions as AzureSearchRAG: async, AzureKeyCredential,
    graceful degradation when credentials are absent, explicit close().
    """

    def __init__(self, account_name: str, account_key: str) -> None:
        if not account_name or not account_key:
            self.client = None
            self._table = None
            return
        endpoint = f"https://{account_name}.table.core.windows.net"
        self.client = TableServiceClient(
            endpoint=endpoint,
            credential=AzureKeyCredential(account_key),
        )
        self._table = self.client.get_table_client(_TABLE_NAME)

    async def ensure_table(self) -> None:
        if not self.client:
            return
        try:
            await self.client.create_table_if_not_exists(_TABLE_NAME)
        except HttpResponseError as exc:
            logger.warning("rate_limit: could not ensure table exists: %s", exc)

    async def increment(self, row_key: str, limit: int) -> int:
        """Atomically increment a counter row.

        Returns the new count after increment, or -1 when Table Storage is
        unavailable (caller treats -1 as pass-through / degraded mode).

        Raises ValueError when the counter has reached or exceeded `limit`.
        Uses optimistic concurrency via ETag — retries up to _MAX_RETRIES times
        on conflict before giving up and returning the current count.
        """
        if not self._table:
            return -1

        for attempt in range(_MAX_RETRIES):
            try:
                entity = await self._table.get_entity(
                    partition_key=_PARTITION_KEY,
                    row_key=row_key,
                )
                count: int = entity.get("count", 0)
                if count >= limit:
                    raise ValueError(count)

                entity["count"] = count + 1
                await self._table.update_entity(
                    entity=entity,
                    mode="merge",
                    match_condition=MatchConditions.IfNotModified,
                )
                return count + 1

            except ResourceNotFoundError:
                # Row does not exist yet — create it with count=1.
                if limit < 1:
                    raise ValueError(0)
                try:
                    await self._table.create_entity(
                        entity={
                            "PartitionKey": _PARTITION_KEY,
                            "RowKey": row_key,
                            "count": 1,
                        }
                    )
                    return 1
                except HttpResponseError:
                    # Another replica created the row concurrently — retry.
                    if attempt < _MAX_RETRIES - 1:
                        await asyncio.sleep(0.05 * (attempt + 1))
                        continue
                    return -1

            except HttpResponseError as exc:
                # ETag mismatch (412) or transient error — retry.
                logger.debug("rate_limit: ETag conflict on attempt %d: %s", attempt, exc)
                if attempt < _MAX_RETRIES - 1:
                    await asyncio.sleep(0.05 * (attempt + 1))
                    continue
                return -1

        return -1

    async def get_count(self, row_key: str) -> Optional[int]:
        if not self._table:
            return None
        try:
            entity = await self._table.get_entity(
                partition_key=_PARTITION_KEY,
                row_key=row_key,
            )
            return int(entity.get("count", 0))
        except ResourceNotFoundError:
            return 0
        except HttpResponseError:
            return None

    async def close(self) -> None:
        if self.client:
            await self.client.close()
