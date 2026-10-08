"""trace local drafts back to saved platform artifact revisions

Revision ID: 0007_draft_sources
Revises: 0006_wechat_drafts
"""

from alembic import op
import sqlalchemy as sa


revision = "0007_draft_sources"
down_revision = "0006_wechat_drafts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("wechat_drafts", sa.Column("source_task_id", sa.String(length=36), nullable=True))
    op.add_column("wechat_drafts", sa.Column("source_artifact_id", sa.String(length=36), nullable=True))
    op.add_column("wechat_drafts", sa.Column("source_revision_id", sa.String(length=36), nullable=True))
    op.create_index("ix_wechat_drafts_source_revision", "wechat_drafts", ["source_revision_id"])


def downgrade() -> None:
    op.drop_index("ix_wechat_drafts_source_revision", table_name="wechat_drafts")
    op.drop_column("wechat_drafts", "source_revision_id")
    op.drop_column("wechat_drafts", "source_artifact_id")
    op.drop_column("wechat_drafts", "source_task_id")
