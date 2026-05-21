"""Enable pg_trgm extension

Revision ID: 002_enable_pg_trgm
Revises: 001_initial_schema
Create Date: 2026-05-22 00:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "002_enable_pg_trgm"
down_revision: str | None = "001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Ensure pg_trgm extension exists for similarity/search operators
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")


def downgrade() -> None:
    # Drop the extension on downgrade
    op.execute("DROP EXTENSION IF EXISTS pg_trgm")
