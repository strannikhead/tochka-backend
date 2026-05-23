"""Add session_id to cart_items for guest cart support.

Revision ID: 002_cart_guest_session
Revises: 001_initial_schema
Create Date: 2026-05-13 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "002_cart_guest_session"
down_revision: str | None = "001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Make user_id nullable to support guest carts
    op.alter_column("cart_items", "user_id", nullable=True)

    # Add session_id for guest identification (opaque string, e.g. "sess-<uuid>")
    op.add_column(
        "cart_items",
        sa.Column("session_id", sa.String(length=255), nullable=True),
    )
    op.create_index("ix_cart_items_session_id", "cart_items", ["session_id"])

    # Enforce: every row must have either user_id or session_id
    op.create_check_constraint(
        "cart_identity_check",
        "cart_items",
        "user_id IS NOT NULL OR session_id IS NOT NULL",
    )


def downgrade() -> None:
    op.drop_constraint("cart_identity_check", "cart_items", type_="check")
    op.drop_index("ix_cart_items_session_id", table_name="cart_items")
    op.drop_column("cart_items", "session_id")
    op.alter_column("cart_items", "user_id", nullable=False)
