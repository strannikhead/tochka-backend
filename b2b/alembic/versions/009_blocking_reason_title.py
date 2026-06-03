"""Add blocking_reason_title to products

Revision ID: 009_blocking_reason_title
Revises: 835ba8c7ab5e
Create Date: 2026-05-31 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "009_blocking_reason_title"
down_revision: str | None = "835ba8c7ab5e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("products", sa.Column("blocking_reason_title", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("products", "blocking_reason_title")
