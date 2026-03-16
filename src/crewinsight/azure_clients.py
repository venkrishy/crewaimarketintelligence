from __future__ import annotations

from typing import List

from azure.core.credentials import AzureKeyCredential
from azure.search.documents.aio import SearchClient
from azure.search.documents.models import QueryType


class AzureSearchRAG:
    def __init__(self, endpoint: str, api_key: str, index_name: str):
        if not endpoint or not api_key or not index_name:
            self.client = None
            return
        self.client = SearchClient(
            endpoint=endpoint,
            index_name=index_name,
            credential=AzureKeyCredential(api_key),
        )

    async def query(self, query_text: str, top_k: int = 5) -> List[str]:
        if not query_text:
            return []
        if not self.client:
            return []
        results = await self.client.search(
            search_text=query_text,
            top=top_k,
            query_type=QueryType.SIMPLE,
        )
        docs: List[str] = []
        async for doc in results:
            if doc.get("content"):
                docs.append(doc.get("content"))
        return docs

    async def close(self) -> None:
        if self.client:
            await self.client.close()
