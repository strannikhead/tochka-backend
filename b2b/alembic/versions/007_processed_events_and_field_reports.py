"""Add processed_events ledger and product field_reports

Revision ID: 007_processed_events_and_field_reports
Revises: 006_product_deleted_flag
Create Date: 2026-05-30 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

# revision identifiers, used by Alembic.
revision: str = "007_processed_events_and_field_reports"
down_revision: str | None = "006_product_deleted_flag"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Per-field moderation remarks from the last BLOCKED decision.
    op.add_column(
        "products",
        sa.Column("field_reports", JSONB(), nullable=False, server_default="[]"),
    )

    # Idempotency ledger for inbound moderation events.
    op.create_table(
        "processed_events",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("sender_service", sa.String(length=50), nullable=False),
        sa.Column("idempotency_key", UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column("product_id", UUID(as_uuid=True), nullable=True),
        sa.Column(
            "processed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "sender_service", "idempotency_key", name="uq_processed_events_sender_key"
        ),
    )


def downgrade() -> None:
    op.drop_table("processed_events")
    op.drop_column("products", "field_reports")
