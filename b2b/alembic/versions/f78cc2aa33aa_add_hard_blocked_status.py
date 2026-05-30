"""add_hard_blocked_status

Revision ID: f78cc2aa33aa
Revises: 004_product_card_fields
Create Date: 2026-05-31 00:12:28.705332

"""

from collections.abc import Sequence

from alembic import op

revision: str = "f78cc2aa33aa"
down_revision: str | None = "004_product_card_fields"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE product_status ADD VALUE IF NOT EXISTS 'HARD_BLOCKED'")


def downgrade() -> None:
    # Postgres does not support removing enum values; downgrade is a no-op.
    pass
