"""Add product card fields (blocking + SKU seller fields)

Revision ID: 004_product_card_fields
Revises: 003_product_seller_id_slug
Create Date: 2026-05-24 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision: str = "004_product_card_fields"
down_revision: str | None = "003_product_seller_id_slug"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Product: blocking metadata set by Moderation Service on BLOCKED.
    op.add_column(
        "products", sa.Column("blocking_reason_id", UUID(as_uuid=True), nullable=True)
    )
    op.add_column("products", sa.Column("moderator_comment", sa.Text(), nullable=True))

    # SKU: seller-view economics. cost_price / reserved_quantity stay seller-only.
    op.add_column(
        "skus", sa.Column("discount", sa.Integer(), nullable=False, server_default="0")
    )
    op.add_column("skus", sa.Column("cost_price", sa.Integer(), nullable=True))
    op.add_column(
        "skus", sa.Column("stock_quantity", sa.Integer(), nullable=False, server_default="0")
    )
    op.add_column(
        "skus", sa.Column("reserved_quantity", sa.Integer(), nullable=False, server_default="0")
    )
    op.add_column("skus", sa.Column("article", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("skus", "article")
    op.drop_column("skus", "reserved_quantity")
    op.drop_column("skus", "stock_quantity")
    op.drop_column("skus", "cost_price")
    op.drop_column("skus", "discount")
    op.drop_column("products", "moderator_comment")
    op.drop_column("products", "blocking_reason_id")
