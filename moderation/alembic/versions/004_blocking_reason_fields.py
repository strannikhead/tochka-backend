"""Add title and hard_block to blocking_reasons

Revision ID: 004_blocking_reason_fields
Revises: 003_b2b_events
Create Date: 2026-06-05 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "004_blocking_reason_fields"
down_revision: str | None = "003_b2b_events"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Unified reason name shown to sellers; existing seed rows default to empty title.
    op.add_column(
        "blocking_reasons",
        sa.Column("title", sa.String(length=200), nullable=False, server_default=""),
    )
    # Soft vs hard block routing; existing reasons default to soft (false).
    op.add_column(
        "blocking_reasons",
        sa.Column("hard_block", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    # description is optional per the OpenAPI contract.
    op.alter_column("blocking_reasons", "description", existing_type=sa.Text(), nullable=True)


def downgrade() -> None:
    op.alter_column("blocking_reasons", "description", existing_type=sa.Text(), nullable=False)
    op.drop_column("blocking_reasons", "hard_block")
    op.drop_column("blocking_reasons", "title")
