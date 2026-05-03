"""Initial schema for Moderation service

Revision ID: 001_initial_schema
Revises:
Create Date: 2026-04-22 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

# revision identifiers, used by Alembic.
revision: str = "001_initial_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Enum type will be created automatically by SQLAlchemy when creating the table

    # Create product_snapshots table
    op.create_table(
        "product_snapshots",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("product_id", UUID(as_uuid=True), nullable=False),
        sa.Column("snapshot_data", JSONB(), nullable=False),
        sa.Column("is_moderated", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_product_snapshots_product_id"), "product_snapshots", ["product_id"])
    op.create_index(
        op.f("ix_product_snapshots_is_moderated"), "product_snapshots", ["is_moderated"]
    )

    # Create blocking_reasons table
    op.create_table(
        "blocking_reasons",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_blocking_reasons_code"), "blocking_reasons", ["code"], unique=True)

    # Create moderation_decisions table
    op.create_table(
        "moderation_decisions",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("snapshot_id", UUID(as_uuid=True), nullable=False),
        sa.Column(
            "decision",
            sa.Enum("APPROVED", "DECLINED", name="moderation_decision_type"),
            nullable=False,
        ),
        sa.Column("reason_id", UUID(as_uuid=True), nullable=True),
        sa.Column("moderator_id", UUID(as_uuid=True), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["snapshot_id"],
            ["product_snapshots.id"],
        ),
        sa.ForeignKeyConstraint(
            ["reason_id"],
            ["blocking_reasons.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_moderation_decisions_snapshot_id"), "moderation_decisions", ["snapshot_id"]
    )
    op.create_index(
        op.f("ix_moderation_decisions_moderator_id"), "moderation_decisions", ["moderator_id"]
    )

    # Insert default blocking reasons
    op.execute("""
        INSERT INTO blocking_reasons (id, code, description, is_active, created_at) VALUES
        (gen_random_uuid(), 'INAPPROPRIATE_CONTENT', 'Неприемлемый контент или изображения', true, now()),
        (gen_random_uuid(), 'INCORRECT_CATEGORY', 'Неверная категория товара', true, now()),
        (gen_random_uuid(), 'INCOMPLETE_INFO', 'Неполная информация о товаре', true, now()),
        (gen_random_uuid(), 'PROHIBITED_ITEM', 'Запрещенный товар', true, now()),
        (gen_random_uuid(), 'SPAM', 'Спам или дублирование', true, now())
    """)  # noqa: E501


def downgrade() -> None:
    op.drop_index(op.f("ix_moderation_decisions_moderator_id"), table_name="moderation_decisions")
    op.drop_index(op.f("ix_moderation_decisions_snapshot_id"), table_name="moderation_decisions")
    op.drop_table("moderation_decisions")
    op.drop_index(op.f("ix_blocking_reasons_code"), table_name="blocking_reasons")
    op.drop_table("blocking_reasons")
    op.drop_index(op.f("ix_product_snapshots_is_moderated"), table_name="product_snapshots")
    op.drop_index(op.f("ix_product_snapshots_product_id"), table_name="product_snapshots")
    op.drop_table("product_snapshots")
    op.execute("DROP TYPE moderation_decision_type")
