"""initial CreatorOS schema

Revision ID: 0001_initial
Revises:
"""

from alembic import op
import sqlalchemy as sa


revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "creator_profiles",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("current_version_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "creator_profile_versions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("profile_id", sa.String(length=36), nullable=False),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("parent_version_id", sa.String(length=36), nullable=True),
        sa.Column("snapshot_json", sa.JSON(), nullable=False),
        sa.Column("change_summary", sa.String(length=500), nullable=False),
        sa.Column("confirmation_status", sa.String(length=32), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["profile_id"], ["creator_profiles.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("profile_id", "version_no", name="uq_profile_version_number"),
    )
    op.create_index(
        "ix_profile_versions_profile_created",
        "creator_profile_versions",
        ["profile_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_profile_versions_profile_created", table_name="creator_profile_versions")
    op.drop_table("creator_profile_versions")
    op.drop_table("creator_profiles")
