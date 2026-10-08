"""store real connector submission receipts"""

from alembic import op
import sqlalchemy as sa


revision = "0008_connector_receipts"
down_revision = "0007_draft_sources"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("wechat_drafts", sa.Column("remote_id", sa.String(length=200), nullable=True))
    op.add_column("wechat_drafts", sa.Column("submission_receipt_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")))


def downgrade() -> None:
    op.drop_column("wechat_drafts", "submission_receipt_json")
    op.drop_column("wechat_drafts", "remote_id")
