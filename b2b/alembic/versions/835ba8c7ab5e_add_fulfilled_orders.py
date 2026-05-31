"""add_fulfilled_orders

Revision ID: 835ba8c7ab5e
Revises: 91bdca75011d
Create Date: 2026-05-31 19:56:15.787142

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "835ba8c7ab5e"
down_revision: str | None = "91bdca75011d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "inventory_reservations",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("order_id", UUID(as_uuid=True), nullable=False),
        sa.Column("idempotency_key", UUID(as_uuid=True), nullable=False),
        sa.Column(
            "status",
            sa.Enum("RESERVED", "UNRESERVED", name="inventory_reservation_status"),
            nullable=False,
        ),
        sa.Column("failed_items", sa.JSON(), nullable=False),
        sa.Column("reserved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key", name="uq_inventory_reservations_idempotency_key"),
    )
    op.create_index(
        op.f("ix_inventory_reservations_idempotency_key"),
        "inventory_reservations",
        ["idempotency_key"],
        unique=False,
    )
    op.create_index(
        op.f("ix_inventory_reservations_order_id"),
        "inventory_reservations",
        ["order_id"],
        unique=False,
    )

    op.create_table(
        "inventory_reservation_items",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("reservation_id", UUID(as_uuid=True), nullable=False),
        sa.Column("sku_id", UUID(as_uuid=True), nullable=False),
        sa.Column("requested", sa.Integer(), nullable=False),
        sa.Column("remaining_stock", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(["reservation_id"], ["inventory_reservations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_inventory_reservation_items_reservation_id"),
        "inventory_reservation_items",
        ["reservation_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_inventory_reservation_items_sku_id"),
        "inventory_reservation_items",
        ["sku_id"],
        unique=False,
    )

    op.create_table(
        "fulfilled_orders",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("order_id", UUID(as_uuid=True), nullable=False),
        sa.Column("fulfilled_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("order_id", name="uq_fulfilled_orders_order_id"),
    )
    op.create_index(
        op.f("ix_fulfilled_orders_order_id"),
        "fulfilled_orders",
        ["order_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_fulfilled_orders_order_id"), table_name="fulfilled_orders")
    op.drop_table("fulfilled_orders")
    op.drop_index(
        op.f("ix_inventory_reservation_items_sku_id"),
        table_name="inventory_reservation_items",
    )
    op.drop_index(
        op.f("ix_inventory_reservation_items_reservation_id"),
        table_name="inventory_reservation_items",
    )
    op.drop_table("inventory_reservation_items")
    op.drop_index(op.f("ix_inventory_reservations_order_id"), table_name="inventory_reservations")
    op.drop_index(
        op.f("ix_inventory_reservations_idempotency_key"), table_name="inventory_reservations"
    )
    op.drop_table("inventory_reservations")
    op.execute("DROP TYPE IF EXISTS inventory_reservation_status")
