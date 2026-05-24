"""Add seller_id and slug to products

Revision ID: 003_product_seller_id_slug
Revises: 002_enable_pg_trgm
Create Date: 2026-05-24 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision: str = "003_product_seller_id_slug"
down_revision: str | None = "002_enable_pg_trgm"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # seller_id is the owning seller's id, taken from the JWT on creation (never from body).
    op.add_column("products", sa.Column("seller_id", UUID(as_uuid=True), nullable=False))
    op.add_column("products", sa.Column("slug", sa.String(length=512), nullable=True))
    op.create_index(op.f("ix_products_seller_id"), "products", ["seller_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_products_seller_id"), table_name="products")
    op.drop_column("products", "slug")
    op.drop_column("products", "seller_id")
