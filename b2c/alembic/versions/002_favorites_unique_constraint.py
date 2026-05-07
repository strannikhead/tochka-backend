"""Add unique constraint on favorites(user_id, product_id)

Revision ID: 002_favorites_unique_constraint
Revises: 001_initial_schema
Create Date: 2026-05-07 00:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

revision: str = "002_favorites_unique_constraint"
down_revision: str | None = "001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_favorites_user_product",
        "favorites",
        ["user_id", "product_id"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_favorites_user_product", "favorites", type_="unique")
