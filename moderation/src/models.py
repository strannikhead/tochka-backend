"""Database models for Moderation service."""

from __future__ import annotations

import enum
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""

    pass


class ModerationDecisionType(enum.Enum):
    """Moderation decision type enum."""

    APPROVED = "APPROVED"
    DECLINED = "DECLINED"


class TicketKind(enum.Enum):
    """Moderation ticket kind from moderation/openapi.yaml."""

    CREATE = "CREATE"
    EDIT = "EDIT"


class TicketStatus(enum.Enum):
    """Moderation ticket status from moderation/openapi.yaml."""

    PENDING = "PENDING"
    IN_REVIEW = "IN_REVIEW"
    APPROVED = "APPROVED"
    BLOCKED = "BLOCKED"
    HARD_BLOCKED = "HARD_BLOCKED"


class FieldReportSeverity(enum.Enum):
    """Per-field moderation report severity."""

    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


class B2BEventType(enum.Enum):
    """Inbound B2B event type from moderation/openapi.yaml."""

    PRODUCT_CREATED = "PRODUCT_CREATED"
    PRODUCT_EDITED = "PRODUCT_EDITED"
    PRODUCT_DELETED = "PRODUCT_DELETED"


class ProductSnapshot(Base):
    """Product snapshot for moderation."""

    __tablename__ = "product_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    snapshot_data: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    is_moderated: Mapped[bool] = mapped_column(Integer, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )

    decisions: Mapped[list[ModerationDecision]] = relationship(
        "ModerationDecision", back_populates="snapshot"
    )


class BlockingReason(Base):
    """Blocking reason reference."""

    __tablename__ = "blocking_reasons"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Integer, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )

    decisions: Mapped[list[ModerationDecision]] = relationship(
        "ModerationDecision", back_populates="reason"
    )


class ModerationDecision(Base):
    """Moderation decision."""

    __tablename__ = "moderation_decisions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    snapshot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("product_snapshots.id"), nullable=False, index=True
    )
    decision: Mapped[ModerationDecisionType] = mapped_column(
        Enum(ModerationDecisionType, name="moderation_decision_type"), nullable=False
    )
    reason_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("blocking_reasons.id"), nullable=True
    )
    moderator_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )

    snapshot: Mapped[ProductSnapshot] = relationship("ProductSnapshot", back_populates="decisions")
    reason: Mapped[BlockingReason | None] = relationship(
        "BlockingReason", back_populates="decisions"
    )


class ProductModeration(Base):
    """Moderation ticket — one per product."""

    __tablename__ = "product_moderation"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), unique=True, nullable=False, index=True
    )
    seller_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    category_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    kind: Mapped[str] = mapped_column(String(10), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING", index=True)
    queue_priority: Mapped[int] = mapped_column(Integer, nullable=False)
    json_before: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    json_after: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    blocking_reason_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    moderator_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    moderator_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    claim_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    date_created: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    date_updated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    date_moderation: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    field_reports: Mapped[list[FieldReport]] = relationship(
        "FieldReport", back_populates="ticket", cascade="all, delete-orphan"
    )


class FieldReport(Base):
    """Per-field report attached to a moderation ticket."""

    __tablename__ = "field_reports"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ticket_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("product_moderation.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    field_path: Mapped[str] = mapped_column(String(512), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[FieldReportSeverity] = mapped_column(
        Enum(FieldReportSeverity, name="field_report_severity"),
        nullable=False,
        default=FieldReportSeverity.ERROR,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )

    ticket: Mapped[ProductModeration] = relationship(
        "ProductModeration", back_populates="field_reports"
    )


class ProcessedB2BEvent(Base):
    """Inbound B2B idempotency ledger."""

    __tablename__ = "processed_b2b_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    idempotency_key: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, unique=True, index=True
    )
    event_type: Mapped[B2BEventType] = mapped_column(
        Enum(B2BEventType, name="b2b_event_type"), nullable=False
    )
    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
