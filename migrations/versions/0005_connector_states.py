"""local connector state and audit events

Revision ID: 0005_connector_states
Revises: 0004_input_metadata
"""

from alembic import op
import sqlalchemy as sa


revision = "0005_connector_states"
down_revision = "0004_input_metadata"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "connector_states",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("connector_key", sa.String(length=64), nullable=False),
        sa.Column("platform", sa.String(length=32), nullable=False),
        sa.Column("label", sa.String(length=120), nullable=False),
        sa.Column("adapter_kind", sa.String(length=32), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("last_operation", sa.String(length=32), nullable=True),
        sa.Column("last_error_code", sa.String(length=64), nullable=True),
        sa.Column("last_error", sa.String(length=500), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("connector_key", name="uq_connector_state_key"),
    )
    op.create_table(
        "connector_events",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("connector_key", sa.String(length=64), nullable=False),
        sa.Column("operation", sa.String(length=32), nullable=False),
        sa.Column("from_state", sa.String(length=32), nullable=True),
        sa.Column("to_state", sa.String(length=32), nullable=False),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_connector_events_connector_created", "connector_events", ["connector_key", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_connector_events_connector_created", table_name="connector_events")
    op.drop_table("connector_events")
    op.drop_table("connector_states")
