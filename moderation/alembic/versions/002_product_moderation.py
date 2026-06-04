"""Add product_moderation table

Revision ID: 002_product_moderation
Revises: 001_initial_schema
Create Date: 2026-06-04 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "002_product_moderation"
down_revision: str | None = "001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "product_moderation",
        sa.Column("id", UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("product_id", UUID(as_uuid=True), nullable=False),
        sa.Column("seller_id", UUID(as_uuid=True), nullable=False),
        sa.Column("category_id", UUID(as_uuid=True), nullable=True),
        sa.Column("kind", sa.String(10), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="PENDING"),
        sa.Column("queue_priority", sa.Integer(), nullable=False),
        sa.Column("json_before", JSONB(), nullable=True),
        sa.Column("json_after", JSONB(), nullable=False),
        sa.Column("blocking_reason_id", UUID(as_uuid=True), nullable=True),
        sa.Column("moderator_id", UUID(as_uuid=True), nullable=True),
        sa.Column("moderator_comment", sa.Text(), nullable=True),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("claim_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("date_created", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("date_updated", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("date_moderation", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("product_id"),
        sa.CheckConstraint("queue_priority BETWEEN 1 AND 4", name="ck_queue_priority_range"),
    )
    op.create_index("ix_product_moderation_product_id", "product_moderation", ["product_id"], unique=True)
    op.create_index("ix_product_moderation_status", "product_moderation", ["status"])
    op.create_index(
        "ix_product_moderation_status_priority",
        "product_moderation",
        ["status", "queue_priority", "date_updated"],
    )


def downgrade() -> None:
    op.drop_index("ix_product_moderation_status_priority", table_name="product_moderation")
    op.drop_index("ix_product_moderation_status", table_name="product_moderation")
    op.drop_index("ix_product_moderation_product_id", table_name="product_moderation")
    op.drop_table("product_moderation")
