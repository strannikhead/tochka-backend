"""add_moderation_outbox

Revision ID: 91bdca75011d
Revises: f78cc2aa33aa
Create Date: 2026-05-31 00:35:48.772168

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "91bdca75011d"
down_revision: str | None = "f78cc2aa33aa"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "moderation_outbox",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("idempotency_key", UUID(as_uuid=True), nullable=False),
        sa.Column("product_id", UUID(as_uuid=True), nullable=False),
        sa.Column("seller_id", UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column(
            "status",
            sa.Enum("PENDING", "SENT", name="outbox_status"),
            nullable=False,
            server_default="PENDING",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key", name="uq_moderation_outbox_idempotency_key"),
    )


def downgrade() -> None:
    op.drop_table("moderation_outbox")
    op.execute("DROP TYPE outbox_status")
