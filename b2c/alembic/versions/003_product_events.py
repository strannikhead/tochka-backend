"""Add B2C product event idempotency and cart unavailability state.

Revision ID: 003_product_events
Revises: 002_cart_guest_session, 002_favorites_unique_constraint
Create Date: 2026-05-24 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "003_product_events"
down_revision: str | tuple[str, str] | None = (
    "002_cart_guest_session",
    "002_favorites_unique_constraint",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "cart_items",
        sa.Column("unavailable_reason", sa.String(length=50), nullable=True),
    )

    op.create_table(
        "event_idempotency_keys",
        sa.Column("idempotency_key", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("idempotency_key"),
    )


def downgrade() -> None:
    op.drop_table("event_idempotency_keys")
    op.drop_column("cart_items", "unavailable_reason")
