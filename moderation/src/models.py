"""Database models for Moderation service."""
import uuid
from datetime import datetime, UTC
import enum

from sqlalchemy import String, Integer, DateTime, Text, Enum, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""
    pass


class ModerationDecisionType(str, enum.Enum):
    """Moderation decision type enum."""
    APPROVED = "APPROVED"
    DECLINED = "DECLINED"


class ProductSnapshot(Base):
    """Product snapshot for moderation."""
    __tablename__ = "product_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    snapshot_data: Mapped[dict] = mapped_column(JSONB, nullable=False)
    is_moderated: Mapped[bool] = mapped_column(Integer, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))

    # Relationships
    decisions: Mapped[list["ModerationDecision"]] = relationship("ModerationDecision", back_populates="snapshot")


class BlockingReason(Base):
    """Blocking reason reference."""
    __tablename__ = "blocking_reasons"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Integer, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))

    # Relationships
    decisions: Mapped[list["ModerationDecision"]] = relationship("ModerationDecision", back_populates="reason")


class ModerationDecision(Base):
    """Moderation decision."""
    __tablename__ = "moderation_decisions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    snapshot_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("product_snapshots.id"), nullable=False, index=True)
    decision: Mapped[ModerationDecisionType] = mapped_column(Enum(ModerationDecisionType, name="moderation_decision_type"), nullable=False)
    reason_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("blocking_reasons.id"), nullable=True)
    moderator_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))

    # Relationships
    snapshot: Mapped["ProductSnapshot"] = relationship("ProductSnapshot", back_populates="decisions")
    reason: Mapped["BlockingReason | None"] = relationship("BlockingReason", back_populates="decisions")
