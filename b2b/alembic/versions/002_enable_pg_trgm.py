"""Enable pg_trgm extension and indexes

Revision ID: 002_enable_pg_trgm
Revises: 001_initial_schema
Create Date: 2026-05-10 00:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "002_enable_pg_trgm"
down_revision: str | None = "001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.create_index(
        "ix_products_title_trgm",
        "products",
        ["title"],
        postgresql_using="gin",
        postgresql_ops={"title": "gin_trgm_ops"},
    )
    op.create_index(
        "ix_products_description_trgm",
        "products",
        ["description"],
        postgresql_using="gin",
        postgresql_ops={"description": "gin_trgm_ops"},
    )


def downgrade() -> None:
    op.drop_index("ix_products_description_trgm", table_name="products")
    op.drop_index("ix_products_title_trgm", table_name="products")
    op.execute("DROP EXTENSION IF EXISTS pg_trgm")
