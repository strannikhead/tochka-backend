"""Add B2B event intake tables

Revision ID: 003_b2b_events
Revises: 002_product_moderation
Create Date: 2026-06-04 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision: str = "003_b2b_events"
down_revision: str | None = "002_product_moderation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    field_report_severity = sa.Enum("INFO", "WARNING", "ERROR", name="field_report_severity")
    b2b_event_type = sa.Enum(
        "PRODUCT_CREATED", "PRODUCT_EDITED", "PRODUCT_DELETED", name="b2b_event_type"
    )

    bind = op.get_bind()
    field_report_severity.create(bind, checkfirst=True)
    b2b_event_type.create(bind, checkfirst=True)

    op.create_table(
        "field_reports",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("ticket_id", UUID(as_uuid=True), nullable=False),
        sa.Column("field_path", sa.String(length=512), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("severity", field_report_severity, nullable=False, server_default="ERROR"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["ticket_id"], ["product_moderation.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_field_reports_ticket_id"), "field_reports", ["ticket_id"])

    op.create_table(
        "processed_b2b_events",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("idempotency_key", UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", b2b_event_type, nullable=False),
        sa.Column("product_id", UUID(as_uuid=True), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "processed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key", name="uq_processed_b2b_events_idempotency_key"),
    )
    op.create_index(
        op.f("ix_processed_b2b_events_idempotency_key"),
        "processed_b2b_events",
        ["idempotency_key"],
        unique=True,
    )
    op.create_index(
        op.f("ix_processed_b2b_events_product_id"), "processed_b2b_events", ["product_id"]
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_processed_b2b_events_product_id"), table_name="processed_b2b_events")
    op.drop_index(
        op.f("ix_processed_b2b_events_idempotency_key"), table_name="processed_b2b_events"
    )
    op.drop_table("processed_b2b_events")
    op.drop_index(op.f("ix_field_reports_ticket_id"), table_name="field_reports")
    op.drop_table("field_reports")

    bind = op.get_bind()
    sa.Enum(name="b2b_event_type").drop(bind, checkfirst=True)
    sa.Enum(name="field_report_severity").drop(bind, checkfirst=True)
