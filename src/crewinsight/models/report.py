from __future__ import annotations

from enum import Enum
from typing import Dict, List

from pydantic import BaseModel, Field


class CrewRunStatus(str, Enum):
    pending = "pending"
    running = "running"
    complete = "complete"
    failed = "failed"


class CrewRunRequest(BaseModel):
    company: str = Field(..., min_length=1)
    segment: str = Field(..., min_length=1)


class CompetitorProfile(BaseModel):
    name: str
    overview: str
    key_products: List[str]
    pricing: str
    news_highlights: List[str]


class Recommendation(BaseModel):
    title: str
    rationale: str
    expected_impact: str


class ReportMetadata(BaseModel):
    run_id: str
    company: str = ""
    segment: str = ""
    duration_seconds: float
    total_tokens: int
    cost_usd: float
    total_agents: int = 4
    created_at: str = ""


class CrewReport(BaseModel):
    executive_summary: str
    company_overview: Dict[str, str]
    competitors: List[CompetitorProfile]
    swot: Dict[str, List[str]]
    recommendations: List[Recommendation]
    sources: List[str]
    metadata: ReportMetadata
