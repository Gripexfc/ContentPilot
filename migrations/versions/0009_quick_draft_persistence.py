"""bind browser quick drafts to content tasks"""

from alembic import op
import sqlalchemy as sa


revision = "0009_quick_draft_persistence"
down_revision = "0008_connector_receipts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("content_tasks", sa.Column("quick_draft_id", sa.String(length=64), nullable=True))
    op.create_index("uq_content_tasks_quick_draft_id", "content_tasks", ["quick_draft_id"], unique=True)


def downgrade() -> None:
    op.drop_index("uq_content_tasks_quick_draft_id", table_name="content_tasks")
    op.drop_column("content_tasks", "quick_draft_id")
