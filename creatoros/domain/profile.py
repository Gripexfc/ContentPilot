from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Identity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str = ""
    profession: str = ""
    bio: str = ""


class Experience(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=120)
    detail: str = Field(default="", max_length=2000)
    occurred_at: Optional[str] = None


class ReaderProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    problems: List[str] = Field(default_factory=list)


class Voice(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tone: str = ""
    examples: List[str] = Field(default_factory=list)


class Boundaries(BaseModel):
    model_config = ConfigDict(extra="forbid")

    forbidden_words: List[str] = Field(default_factory=list)
    sensitive_topics: List[str] = Field(default_factory=list)
    unwanted_expressions: List[str] = Field(default_factory=list)


class PlatformProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    positioning: str = ""
    audience: str = ""
    format_preferences: List[str] = Field(default_factory=list)
    tone: str = ""


class ContentDefaults(BaseModel):
    model_config = ConfigDict(extra="forbid")

    positioning: str = ""
    format_preferences: List[str] = Field(default_factory=list)


class Goals(BaseModel):
    model_config = ConfigDict(extra="forbid")

    priorities: List[str] = Field(default_factory=list)


class ProfileSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    identity: Identity = Field(default_factory=Identity)
    experiences: List[Experience] = Field(default_factory=list)
    domains: List[str] = Field(default_factory=list)
    pillars: List[str] = Field(default_factory=list)
    readers: List[ReaderProfile] = Field(default_factory=list)
    voice: Voice = Field(default_factory=Voice)
    boundaries: Boundaries = Field(default_factory=Boundaries)
    platforms: Dict[str, PlatformProfile] = Field(default_factory=dict)
    content_defaults: ContentDefaults = Field(default_factory=ContentDefaults)
    goals: Goals = Field(default_factory=Goals)
    evidence_refs: List[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def ensure_platform_sections(self) -> "ProfileSnapshot":
        for platform in ("wechat", "xiaohongshu", "douyin"):
            self.platforms.setdefault(platform, PlatformProfile())
        return self


class ProfileVersionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    snapshot: ProfileSnapshot
    change_summary: str = Field(default="", max_length=500)
    base_version_id: Optional[str] = None


class ProfileVersionRead(BaseModel):
    id: str
    profile_id: str
    version_no: int
    parent_version_id: Optional[str]
    snapshot: ProfileSnapshot
    change_summary: str
    confirmation_status: str
    confirmed_at: Optional[str]
    created_at: str


class ProfileRead(BaseModel):
    id: str
    current_version_id: str
    current_version: ProfileVersionRead


class ProfileVersionSummary(BaseModel):
    id: str
    version_no: int
    parent_version_id: Optional[str]
    change_summary: str
    confirmation_status: str
    created_at: str


class ProfileDiffItem(BaseModel):
    path: str
    before: object = None
    after: object = None


class ProfileDiffRead(BaseModel):
    left_version_id: str
    right_version_id: str
    changes: List[ProfileDiffItem]
