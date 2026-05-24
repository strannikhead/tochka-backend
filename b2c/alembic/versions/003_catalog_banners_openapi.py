"""Align catalog banners with OpenAPI schedule fields.

Revision ID: 003_catalog_banners_openapi
Revises: 002_cart_guest_session, 002_favorites_unique_constraint
Create Date: 2026-05-24 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "003_catalog_banners_openapi"
down_revision: tuple[str, str] = ("002_cart_guest_session", "002_favorites_unique_constraint")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "banners",
        sa.Column("active_from", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "banners",
        sa.Column("active_to", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute("UPDATE banners SET link = '/' WHERE link IS NULL")
    op.alter_column(
        "banners",
        "link",
        existing_type=sa.String(length=500),
        nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "banners",
        "link",
        existing_type=sa.String(length=500),
        nullable=True,
    )
    op.drop_column("banners", "active_to")
    op.drop_column("banners", "active_from")
