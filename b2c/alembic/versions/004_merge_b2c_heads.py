"""Merge B2C migration heads.

Revision ID: 004_merge_b2c_heads
Revises: 003_catalog_banners_openapi, 003_product_events, 5c17a58cbb19
Create Date: 2026-05-31 00:00:00.000000
"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "004_merge_b2c_heads"
down_revision: tuple[str, str, str] = (
    "003_catalog_banners_openapi",
    "003_product_events",
    "5c17a58cbb19",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
