"""content task, platform artifacts, edits and proposed memories

Revision ID: 0002_content_flow
Revises: 0001_initial
"""

from alembic import op
import sqlalchemy as sa


revision = "0002_content_flow"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "content_tasks",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("profile_version_id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("reader_problem", sa.Text(), nullable=False),
        sa.Column("author_angle", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["profile_version_id"], ["creator_profile_versions.id"]),
    )
    op.create_table(
        "task_inputs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("input_type", sa.String(length=32), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("parse_status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["content_tasks.id"], ondelete="CASCADE"),
    )
    op.create_table(
        "task_events",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("from_status", sa.String(length=32), nullable=True),
        sa.Column("to_status", sa.String(length=32), nullable=True),
        sa.Column("actor", sa.String(length=32), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["content_tasks.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_task_events_task_created", "task_events", ["task_id", "created_at"])
    op.create_table(
        "briefs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("confirmation_status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["content_tasks.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("task_id", "version_no", name="uq_brief_task_version"),
    )
    op.create_table(
        "platform_artifacts",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("platform", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("current_revision_id", sa.String(length=36), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["content_tasks.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("task_id", "platform", name="uq_artifact_task_platform"),
    )
    op.create_table(
        "artifact_revisions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("artifact_id", sa.String(length=36), nullable=False),
        sa.Column("revision_no", sa.Integer(), nullable=False),
        sa.Column("parent_revision_id", sa.String(length=36), nullable=True),
        sa.Column("content_json", sa.JSON(), nullable=False),
        sa.Column("profile_version_id", sa.String(length=36), nullable=False),
        sa.Column("brief_id", sa.String(length=36), nullable=False),
        sa.Column("source_ids_json", sa.JSON(), nullable=False),
        sa.Column("memory_ids_json", sa.JSON(), nullable=False),
        sa.Column("generation_kind", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["artifact_id"], ["platform_artifacts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["profile_version_id"], ["creator_profile_versions.id"]),
        sa.ForeignKeyConstraint(["brief_id"], ["briefs.id"]),
        sa.UniqueConstraint("artifact_id", "revision_no", name="uq_artifact_revision_number"),
    )
    op.create_index("ix_artifact_revisions_artifact_created", "artifact_revisions", ["artifact_id", "created_at"])
    op.create_table(
        "edit_events",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("artifact_revision_id", sa.String(length=36), nullable=False),
        sa.Column("path", sa.String(length=300), nullable=False),
        sa.Column("before_json", sa.JSON(), nullable=True),
        sa.Column("after_json", sa.JSON(), nullable=True),
        sa.Column("reason", sa.String(length=500), nullable=False),
        sa.Column("actor", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["artifact_revision_id"], ["artifact_revisions.id"], ondelete="CASCADE"),
    )
    op.create_table(
        "memories",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("statement", sa.Text(), nullable=False),
        sa.Column("source_event_id", sa.String(length=36), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("scope_json", sa.JSON(), nullable=False),
        sa.Column("confirmation_status", sa.String(length=32), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["source_event_id"], ["edit_events.id"], ondelete="CASCADE"),
    )


def downgrade() -> None:
    op.drop_table("memories")
    op.drop_table("edit_events")
    op.drop_index("ix_artifact_revisions_artifact_created", table_name="artifact_revisions")
    op.drop_table("artifact_revisions")
    op.drop_table("platform_artifacts")
    op.drop_table("briefs")
    op.drop_index("ix_task_events_task_created", table_name="task_events")
    op.drop_table("task_events")
    op.drop_table("task_inputs")
    op.drop_table("content_tasks")
