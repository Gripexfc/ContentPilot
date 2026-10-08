from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from creatoros.db.base import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class CreatorProfile(Base):
    __tablename__ = "creator_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    current_version_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class CreatorProfileVersion(Base):
    __tablename__ = "creator_profile_versions"
    __table_args__ = (
        UniqueConstraint("profile_id", "version_no", name="uq_profile_version_number"),
        Index("ix_profile_versions_profile_created", "profile_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    profile_id: Mapped[str] = mapped_column(
        ForeignKey("creator_profiles.id", ondelete="CASCADE"), nullable=False
    )
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    parent_version_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    snapshot_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    change_summary: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    confirmation_status: Mapped[str] = mapped_column(String(32), default="confirmed", nullable=False)
    confirmed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class ContentTask(Base):
    __tablename__ = "content_tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    quick_draft_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, unique=True)
    profile_version_id: Mapped[str] = mapped_column(
        ForeignKey("creator_profile_versions.id"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="idea")
    reader_problem: Mapped[str] = mapped_column(Text, nullable=False, default="")
    author_angle: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    archived_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class TaskInput(Base):
    __tablename__ = "task_inputs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    task_id: Mapped[str] = mapped_column(ForeignKey("content_tasks.id", ondelete="CASCADE"), nullable=False)
    input_type: Mapped[str] = mapped_column(String(32), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    parse_status: Mapped[str] = mapped_column(String(32), nullable=False, default="ready")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class TaskEvent(Base):
    __tablename__ = "task_events"
    __table_args__ = (Index("ix_task_events_task_created", "task_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    task_id: Mapped[str] = mapped_column(ForeignKey("content_tasks.id", ondelete="CASCADE"), nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    from_status: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    to_status: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    actor: Mapped[str] = mapped_column(String(32), nullable=False, default="user")
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class Brief(Base):
    __tablename__ = "briefs"
    __table_args__ = (UniqueConstraint("task_id", "version_no", name="uq_brief_task_version"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    task_id: Mapped[str] = mapped_column(ForeignKey("content_tasks.id", ondelete="CASCADE"), nullable=False)
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    confirmation_status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class PlatformArtifact(Base):
    __tablename__ = "platform_artifacts"
    __table_args__ = (UniqueConstraint("task_id", "platform", name="uq_artifact_task_platform"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    task_id: Mapped[str] = mapped_column(ForeignKey("content_tasks.id", ondelete="CASCADE"), nullable=False)
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="generated")
    current_revision_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    error_code: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class ArtifactRevision(Base):
    __tablename__ = "artifact_revisions"
    __table_args__ = (
        UniqueConstraint("artifact_id", "revision_no", name="uq_artifact_revision_number"),
        Index("ix_artifact_revisions_artifact_created", "artifact_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    artifact_id: Mapped[str] = mapped_column(ForeignKey("platform_artifacts.id", ondelete="CASCADE"), nullable=False)
    revision_no: Mapped[int] = mapped_column(Integer, nullable=False)
    parent_revision_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    content_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    profile_version_id: Mapped[str] = mapped_column(ForeignKey("creator_profile_versions.id"), nullable=False)
    brief_id: Mapped[str] = mapped_column(ForeignKey("briefs.id"), nullable=False)
    source_ids_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    memory_ids_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    generation_kind: Mapped[str] = mapped_column(String(64), nullable=False, default="demo_deterministic")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class EditEvent(Base):
    __tablename__ = "edit_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    artifact_revision_id: Mapped[str] = mapped_column(ForeignKey("artifact_revisions.id", ondelete="CASCADE"), nullable=False)
    path: Mapped[str] = mapped_column(String(300), nullable=False)
    before_json: Mapped[Any] = mapped_column(JSON, nullable=True)
    after_json: Mapped[Any] = mapped_column(JSON, nullable=True)
    reason: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    actor: Mapped[str] = mapped_column(String(32), nullable=False, default="user")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class Memory(Base):
    __tablename__ = "memories"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    source_event_id: Mapped[str] = mapped_column(ForeignKey("edit_events.id", ondelete="CASCADE"), nullable=False)
    confidence: Mapped[float] = mapped_column(nullable=False, default=0.6)
    scope_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    confirmation_status: Mapped[str] = mapped_column(String(32), nullable=False, default="proposed")
    confirmed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class Hotspot(Base):
    __tablename__ = "hotspots"
    __table_args__ = (Index("ix_hotspots_fetched", "fetched_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    canonical_url: Mapped[str] = mapped_column(String(2000), nullable=False)
    source_name: Mapped[str] = mapped_column(String(200), nullable=False)
    source_kind: Mapped[str] = mapped_column(String(64), nullable=False, default="manual")
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    fact_status: Mapped[str] = mapped_column(String(32), nullable=False, default="unverified")
    heat_status: Mapped[str] = mapped_column(String(32), nullable=False, default="unknown")
    relevance_score: Mapped[Optional[float]] = mapped_column(nullable=True)
    relevance_reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    platform_fit_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    needs_human_review: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class HotspotEvidence(Base):
    __tablename__ = "hotspot_evidence"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    hotspot_id: Mapped[str] = mapped_column(ForeignKey("hotspots.id", ondelete="CASCADE"), nullable=False)
    evidence_type: Mapped[str] = mapped_column(String(64), nullable=False)
    source_url: Mapped[str] = mapped_column(String(2000), nullable=False, default="")
    claim: Mapped[str] = mapped_column(Text, nullable=False, default="")
    value_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    verification_status: Mapped[str] = mapped_column(String(32), nullable=False, default="unverified")
    checked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class MetricImport(Base):
    __tablename__ = "metric_imports"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ready")
    original_name: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)


class MetricObservation(Base):
    __tablename__ = "metric_observations"
    __table_args__ = (UniqueConstraint("import_id", "row_hash", name="uq_metric_import_row_hash"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    import_id: Mapped[str] = mapped_column(ForeignKey("metric_imports.id", ondelete="CASCADE"), nullable=False)
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    content_ref: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    title_ref: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    content_type: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    pillar: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    metrics_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    source_ref: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    row_hash: Mapped[str] = mapped_column(String(64), nullable=False)


class ConnectorState(Base):
    """Local adapter state; it never contains credentials or platform cookies."""

    __tablename__ = "connector_states"
    __table_args__ = (UniqueConstraint("connector_key", name="uq_connector_state_key"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    connector_key: Mapped[str] = mapped_column(String(64), nullable=False)
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    adapter_kind: Mapped[str] = mapped_column(String(32), nullable=False, default="mock")
    state: Mapped[str] = mapped_column(String(32), nullable=False, default="not_configured")
    last_operation: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    last_error_code: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    last_error: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class ConnectorEvent(Base):
    __tablename__ = "connector_events"
    __table_args__ = (Index("ix_connector_events_connector_created", "connector_key", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    connector_key: Mapped[str] = mapped_column(String(64), nullable=False)
    operation: Mapped[str] = mapped_column(String(32), nullable=False)
    from_state: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    to_state: Mapped[str] = mapped_column(String(32), nullable=False)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    error_code: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class Draft(Base):
    __tablename__ = "wechat_drafts"
    __table_args__ = (Index("ix_wechat_drafts_updated", "updated_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    title: Mapped[str] = mapped_column(String(64), nullable=False)
    digest: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    author: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    content_html: Mapped[str] = mapped_column(Text, nullable=False, default="")
    cover_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="writing")
    submitted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    publish_error: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    remote_id: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    submission_receipt_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    source_task_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    source_artifact_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    source_revision_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class DraftEvent(Base):
    __tablename__ = "wechat_draft_events"
    __table_args__ = (Index("ix_wechat_draft_events_draft_created", "draft_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    draft_id: Mapped[str] = mapped_column(ForeignKey("wechat_drafts.id", ondelete="CASCADE"), nullable=False)
    operation: Mapped[str] = mapped_column(String(32), nullable=False)
    from_status: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    to_status: Mapped[str] = mapped_column(String(32), nullable=False)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    error: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
