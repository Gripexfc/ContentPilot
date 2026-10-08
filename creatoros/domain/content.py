from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


TASK_STATUSES = ("idea", "researching", "briefed", "drafting", "adapted", "reviewing", "archived")
PLATFORMS = ("wechat", "xiaohongshu", "douyin")


class ContentTaskCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str = Field(min_length=1, max_length=200)
    input_text: str = Field(default="", max_length=10000)
    input_type: Literal["theme", "url", "notes", "hotspot"] = "theme"
    input_metadata: Dict[str, Any] = Field(default_factory=dict)


class QuickDraftCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    quick_draft_id: str = Field(min_length=1, max_length=64)
    topic: str = Field(min_length=1, max_length=200)
    context: str = Field(default="", max_length=10000)
    source: Dict[str, Any] = Field(default_factory=dict)
    platform: Literal["wechat", "xiaohongshu", "douyin"]
    mode: Literal["文章", "配图", "内容+配图"]
    skill: str = Field(default="", max_length=200)
    workflow_id: Optional[str] = Field(default=None, max_length=64)
    output: str = Field(min_length=1, max_length=200000)
    output_artifact: Optional[str] = Field(default=None, max_length=500)


class QuickDraftRead(BaseModel):
    quick_draft_id: str
    task_id: str
    input_id: str
    input_version: int
    title: str
    context: str = ""
    source: Dict[str, Any] = Field(default_factory=dict)
    platform: Literal["wechat", "xiaohongshu", "douyin"]
    mode: Literal["文章", "配图", "内容+配图"]
    skill: str
    workflow_id: Optional[str] = None
    output_artifact: Optional[str] = None
    output: str
    profile_version_id: str
    persistence_state: Literal["saved_input"] = "saved_input"
    content_status: Literal["draft"] = "draft"
    publish_state: Literal["not_started"] = "not_started"
    created_at: str
    updated_at: str


class ContentTaskRead(BaseModel):
    id: str
    quick_draft_id: Optional[str]
    profile_version_id: str
    title: str
    status: str
    reader_problem: str
    author_angle: str
    created_at: str
    updated_at: str
    archived_at: Optional[str]


class BriefRead(BaseModel):
    id: str
    task_id: str
    version_no: int
    payload: Dict[str, Any]
    confirmation_status: str
    created_at: str


class ArtifactRevisionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: Dict[str, Any]
    base_revision_id: str = Field(min_length=1)
    reason: str = Field(default="", max_length=500)


class BriefRevisionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    base_brief_id: str
    reader_problem: str = Field(min_length=1, max_length=3000)
    author_angle: str = Field(min_length=1, max_length=3000)
    facts: List[str] = Field(default_factory=list, max_length=100)
    sources: List[str] = Field(default_factory=list, max_length=100)
    research_gaps: List[str] = Field(default_factory=list, max_length=100)


class MemoryDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    action: Literal["accept", "reject", "revoke", "edit"]
    statement: Optional[str] = Field(default=None, min_length=1, max_length=3000)


class TaskStatusUpdate(BaseModel):
    status: Literal["reviewing", "archived"]


class ArtifactRead(BaseModel):
    id: str
    task_id: str
    platform: str
    status: str
    current_revision_id: Optional[str]
    current_revision: Optional[Dict[str, Any]]
    created_at: str
    updated_at: str


class MemoryRead(BaseModel):
    id: str
    kind: str
    statement: str
    source_event_id: str
    confidence: float
    scope: Dict[str, Any]
    confirmation_status: str
    confirmed_at: Optional[str]
    created_at: str


class ContentTaskDetail(BaseModel):
    task: ContentTaskRead
    latest_brief: Optional[BriefRead]
    artifacts: List[ArtifactRead]
    memories: List[MemoryRead]
    inputs: List[Dict[str, Any]]
    events: List[Dict[str, Any]]
    briefs: List[BriefRead]


class GenerationResult(BaseModel):
    task: ContentTaskRead
    artifacts: List[ArtifactRead]
