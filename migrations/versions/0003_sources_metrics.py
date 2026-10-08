"""hotspots and metric imports

Revision ID: 0003_sources_metrics
Revises: 0002_content_flow
"""

from alembic import op
import sqlalchemy as sa


revision = "0003_sources_metrics"
down_revision = "0002_content_flow"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "hotspots",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("canonical_url", sa.String(length=2000), nullable=False),
        sa.Column("source_name", sa.String(length=200), nullable=False),
        sa.Column("source_kind", sa.String(length=64), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("fact_status", sa.String(length=32), nullable=False),
        sa.Column("heat_status", sa.String(length=32), nullable=False),
        sa.Column("relevance_score", sa.Float(), nullable=True),
        sa.Column("relevance_reason", sa.Text(), nullable=False),
        sa.Column("platform_fit_json", sa.JSON(), nullable=False),
        sa.Column("needs_human_review", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_hotspots_fetched", "hotspots", ["fetched_at"])
    op.create_table(
        "hotspot_evidence",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("hotspot_id", sa.String(length=36), nullable=False),
        sa.Column("evidence_type", sa.String(length=64), nullable=False),
        sa.Column("source_url", sa.String(length=2000), nullable=False),
        sa.Column("claim", sa.Text(), nullable=False),
        sa.Column("value_json", sa.JSON(), nullable=False),
        sa.Column("verification_status", sa.String(length=32), nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["hotspot_id"], ["hotspots.id"], ondelete="CASCADE"),
    )
    op.create_table(
        "metric_imports",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("platform", sa.String(length=32), nullable=False),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("original_name", sa.String(length=300), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("error_json", sa.JSON(), nullable=False),
    )
    op.create_table(
        "metric_observations",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("import_id", sa.String(length=36), nullable=False),
        sa.Column("platform", sa.String(length=32), nullable=False),
        sa.Column("content_ref", sa.String(length=300), nullable=False),
        sa.Column("title_ref", sa.String(length=500), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("content_type", sa.String(length=64), nullable=False),
        sa.Column("pillar", sa.String(length=200), nullable=False),
        sa.Column("metrics_json", sa.JSON(), nullable=False),
        sa.Column("source_ref", sa.String(length=500), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("row_hash", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(["import_id"], ["metric_imports.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("import_id", "row_hash", name="uq_metric_import_row_hash"),
    )


def downgrade() -> None:
    op.drop_table("metric_observations")
    op.drop_table("metric_imports")
    op.drop_table("hotspot_evidence")
    op.drop_index("ix_hotspots_fetched", table_name="hotspots")
    op.drop_table("hotspots")
