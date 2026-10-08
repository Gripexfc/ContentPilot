"""wechat drafts and cover assets

Revision ID: 0006_wechat_drafts
Revises: 0005_connector_states
"""

from alembic import op
import sqlalchemy as sa


revision = "0006_wechat_drafts"
down_revision = "0005_connector_states"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "wechat_drafts",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("title", sa.String(length=64), nullable=False),
        sa.Column("digest", sa.String(length=120), nullable=False),
        sa.Column("author", sa.String(length=32), nullable=False),
        sa.Column("content_html", sa.Text(), nullable=False),
        sa.Column("cover_path", sa.String(length=500), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("publish_error", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_wechat_drafts_updated", "wechat_drafts", ["updated_at"])
    op.create_table(
        "wechat_draft_events",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("draft_id", sa.String(length=36), nullable=False),
        sa.Column("operation", sa.String(length=32), nullable=False),
        sa.Column("from_status", sa.String(length=32), nullable=True),
        sa.Column("to_status", sa.String(length=32), nullable=False),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("error", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["draft_id"], ["wechat_drafts.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_wechat_draft_events_draft_created", "wechat_draft_events", ["draft_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_wechat_draft_events_draft_created", table_name="wechat_draft_events")
    op.drop_table("wechat_draft_events")
    op.drop_index("ix_wechat_drafts_updated", table_name="wechat_drafts")
    op.drop_table("wechat_drafts")
