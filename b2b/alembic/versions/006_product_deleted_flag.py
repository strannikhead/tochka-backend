"""Add soft-delete flag to products

Revision ID: 006_product_deleted_flag
Revises: 005_add_hard_blocked_and_outbox
Create Date: 2026-05-30 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "006_product_deleted_flag"
down_revision: str | None = "004_product_card_fields"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "products",
        sa.Column("deleted", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    # Carry over any products previously soft-deleted via the legacy DELETED status.
    op.execute("UPDATE products SET deleted = true WHERE status = 'DELETED'")


def downgrade() -> None:
    op.drop_column("products", "deleted")
