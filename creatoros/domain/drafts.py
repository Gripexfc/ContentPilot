from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class DraftCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str = Field(min_length=1, max_length=64)
    digest: str = Field(default="", max_length=120)
    author: str = Field(default="", max_length=32)
    content_html: str = Field(default="", max_length=500000)


class DraftUpdate(DraftCreate):
    pass


class DraftRead(BaseModel):
    id: str
    title: str
    digest: str
    author: str
    content_html: str
    cover_path: Optional[str]
    cover_url: Optional[str]
    status: Literal["writing", "ready", "submitted", "failed"]
    submitted_at: Optional[str]
    publish_error: Optional[str]
    remote_id: Optional[str]
    submission_receipt: Optional[dict]
    source_task_id: Optional[str]
    source_artifact_id: Optional[str]
    source_revision_id: Optional[str]
    created_at: str
    updated_at: str


class DraftEventRead(BaseModel):
    id: str
    operation: str
    from_status: Optional[str]
    to_status: str
    success: bool
    error: Optional[str]
    created_at: str


class DraftDetail(DraftRead):
    events: list[DraftEventRead]


class DraftSubmit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    simulate_failure: bool = False


class DraftFromArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    revision_id: str = Field(min_length=1, max_length=36)
