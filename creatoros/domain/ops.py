from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class HotspotCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str = Field(min_length=1, max_length=300)
    canonical_url: str = Field(min_length=1, max_length=2000)
    source_name: str = Field(min_length=1, max_length=200)
    source_kind: str = Field(default="manual", max_length=64)
    published_at: Optional[datetime] = None
    summary: str = Field(default="", max_length=10000)
    fact_status: str = Field(default="unverified", max_length=32)
    heat_status: str = Field(default="unknown", max_length=32)
    relevance_score: Optional[float] = Field(default=None, ge=0, le=1)
    relevance_reason: str = Field(default="", max_length=3000)
    platform_fit: Dict[str, Any] = Field(default_factory=dict)
    needs_human_review: bool = True
    evidence: List[Dict[str, Any]] = Field(default_factory=list, max_length=50)


class HotspotRead(BaseModel):
    id: str
    title: str
    canonical_url: str
    source_name: str
    source_kind: str
    published_at: Optional[str]
    fetched_at: str
    summary: str
    fact_status: str
    heat_status: str
    relevance_score: Optional[float]
    relevance_reason: str
    platform_fit: Dict[str, Any]
    needs_human_review: bool
    evidence: List[Dict[str, Any]]
    created_at: str


class MetricImportCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    platform: Literal["wechat", "xiaohongshu", "douyin"]
    source_type: Literal["manual_json", "manual_csv", "manual_entry", "acceptance_test"] = "manual_json"
    observed_at: datetime
    original_name: str = Field(default="", max_length=300)
    rows: List[Dict[str, Any]] = Field(min_length=1, max_length=10000)


class MetricImportRead(BaseModel):
    id: str
    platform: str
    source_type: str
    imported_at: str
    observed_at: str
    status: str
    original_name: str
    row_count: int
    error: Dict[str, Any]


class MetricSummary(BaseModel):
    observation_count: int
    import_count: int
    by_platform: Dict[str, int]
    by_pillar: Dict[str, int]
    top_content: List[Dict[str, Any]]
    metrics_by_platform: Dict[str, Dict[str, Any]]
    observations: List[Dict[str, Any]]
    data_quality: Dict[str, Any]
    limitations: List[str]


class OverviewRead(BaseModel):
    active_task_count: int
    task_count: int
    pending_memory_count: int
    pending_source_count: int
    draft_count: int
    pending_draft_count: int
    metric_import_count: int
    last_metric_imported_at: Optional[str]
    read_at: str


class MetricInclusion(BaseModel):
    included: bool


class TrendItemRead(BaseModel):
    id: str
    title: str
    hot: str
    url: str
    rank: int
    summary: str


class TrendFeedRead(BaseModel):
    platform: str
    label: str
    status: Literal["fresh", "cached", "stale", "unavailable"]
    fetched_at: Optional[str]
    source_name: Optional[str]
    source_url: Optional[str]
    error: Optional[str]
    items: List[TrendItemRead]


class TrendsRead(BaseModel):
    trends: List[TrendFeedRead]
    refresh_after_seconds: int
