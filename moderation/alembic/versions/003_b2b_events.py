"""Add B2B event intake tables

Revision ID: 003_b2b_events
Revises: 001_initial_schema
Create Date: 2026-06-04 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

# revision identifiers, used by Alembic.
revision: str = "003_b2b_events"
down_revision: str | None = "002_product_moderation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    ticket_kind = sa.Enum("CREATE", "EDIT", name="ticket_kind")
    ticket_status = sa.Enum(
        "PENDING", "IN_REVIEW", "APPROVED", "BLOCKED", "HARD_BLOCKED", name="ticket_status"
    )
    field_report_severity = sa.Enum("INFO", "WARNING", "ERROR", name="field_report_severity")
    b2b_event_type = sa.Enum(
        "PRODUCT_CREATED", "PRODUCT_EDITED", "PRODUCT_DELETED", name="b2b_event_type"
    )

    bind = op.get_bind()
    ticket_kind.create(bind, checkfirst=True)
    ticket_status.create(bind, checkfirst=True)
    field_report_severity.create(bind, checkfirst=True)
    b2b_event_type.create(bind, checkfirst=True)

    op.create_table(
        "moderation_tickets",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("product_id", UUID(as_uuid=True), nullable=False),
        sa.Column("seller_id", UUID(as_uuid=True), nullable=False),
        sa.Column("category_id", UUID(as_uuid=True), nullable=True),
        sa.Column("kind", ticket_kind, nullable=False),
        sa.Column("status", ticket_status, nullable=False, server_default="PENDING"),
        sa.Column("queue_priority", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("assigned_moderator_id", UUID(as_uuid=True), nullable=True),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("claim_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("json_before", JSONB(), nullable=True),
        sa.Column("json_after", JSONB(), nullable=False),
        sa.Column("decision_comment", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("product_id", name="uq_moderation_tickets_product_id"),
    )
    op.create_index(op.f("ix_moderation_tickets_product_id"), "moderation_tickets", ["product_id"])
    op.create_index(op.f("ix_moderation_tickets_seller_id"), "moderation_tickets", ["seller_id"])
    op.create_index(
        op.f("ix_moderation_tickets_category_id"), "moderation_tickets", ["category_id"]
    )
    op.create_index(
        op.f("ix_moderation_tickets_assigned_moderator_id"),
        "moderation_tickets",
        ["assigned_moderator_id"],
    )

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
        sa.ForeignKeyConstraint(["ticket_id"], ["moderation_tickets.id"], ondelete="CASCADE"),
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
    op.drop_index(
        op.f("ix_moderation_tickets_assigned_moderator_id"), table_name="moderation_tickets"
    )
    op.drop_index(op.f("ix_moderation_tickets_category_id"), table_name="moderation_tickets")
    op.drop_index(op.f("ix_moderation_tickets_seller_id"), table_name="moderation_tickets")
    op.drop_index(op.f("ix_moderation_tickets_product_id"), table_name="moderation_tickets")
    op.drop_table("moderation_tickets")

    bind = op.get_bind()
    sa.Enum(name="b2b_event_type").drop(bind, checkfirst=True)
    sa.Enum(name="field_report_severity").drop(bind, checkfirst=True)
    sa.Enum(name="ticket_status").drop(bind, checkfirst=True)
    sa.Enum(name="ticket_kind").drop(bind, checkfirst=True)
