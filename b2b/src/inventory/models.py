from __future__ import annotations

import enum
import uuid
from datetime import UTC, datetime

from b2b.src.models import Base
from sqlalchemy import JSON, DateTime, Enum, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship


class InventoryReservationStatus(enum.StrEnum):
    RESERVED = "RESERVED"
    UNRESERVED = "UNRESERVED"


class InventoryReservation(Base):
    __tablename__ = "inventory_reservations"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_inventory_reservations_idempotency_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    idempotency_key: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    status: Mapped[InventoryReservationStatus] = mapped_column(
        Enum(InventoryReservationStatus, name="inventory_reservation_status"),
        nullable=False,
        default=InventoryReservationStatus.RESERVED,
    )
    failed_items: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    reserved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    items: Mapped[list[InventoryReservationItem]] = relationship(
        "InventoryReservationItem", back_populates="reservation", cascade="all, delete-orphan"
    )


class InventoryReservationItem(Base):
    __tablename__ = "inventory_reservation_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    reservation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("inventory_reservations.id"), nullable=False, index=True
    )
    sku_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    requested: Mapped[int] = mapped_column(Integer, nullable=False)
    remaining_stock: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str | None] = mapped_column(String(64), nullable=True)

    reservation: Mapped[InventoryReservation] = relationship(
        "InventoryReservation", back_populates="items"
    )
