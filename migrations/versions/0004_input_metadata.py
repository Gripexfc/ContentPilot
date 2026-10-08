"""store input source metadata for links and local assets

Revision ID: 0004_input_metadata
Revises: 0003_sources_metrics
"""

from alembic import op
import sqlalchemy as sa


revision = "0004_input_metadata"
down_revision = "0003_sources_metrics"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("task_inputs", sa.Column("metadata_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")))


def downgrade() -> None:
    op.drop_column("task_inputs", "metadata_json")
