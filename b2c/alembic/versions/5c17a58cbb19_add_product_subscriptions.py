"""add product subscriptions

Revision ID: 5c17a58cbb19
Revises: 001_initial_schema
Create Date: 2026-05-10 20:41:54.097702

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "5c17a58cbb19"
down_revision: str | None = "001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "product_subscriptions",
        sa.Column(
            "id",
            sa.UUID(),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("product_id", sa.UUID(), nullable=False),
        sa.Column("events", postgresql.ARRAY(sa.String()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "product_id",
            name="uq_product_subscription_user_product",
        ),
    )

    op.create_index(
        op.f("ix_product_subscriptions_product_id"),
        "product_subscriptions",
        ["product_id"],
        unique=False,
    )

    op.create_index(
        op.f("ix_product_subscriptions_user_id"),
        "product_subscriptions",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_product_subscriptions_user_id"),
        table_name="product_subscriptions",
    )

    op.drop_index(
        op.f("ix_product_subscriptions_product_id"),
        table_name="product_subscriptions",
    )

    op.drop_table("product_subscriptions")
