"""Order models — real, fulfillable customer transactions.

An Order is the heart of the system: a customer, a set of line items, a
status as it moves through the bakery's day, and a stored total.

Key principle — SNAPSHOTTING:
  Order items copy the product's name, price, and unit label at creation
  time. They are historical records of what was actually sold. If a product
  is later renamed, repriced, or deleted, existing orders stay correct. The
  product_id FK remains for linking/analytics, but the displayed values come
  from the snapshot, not the live product.

Relationships:
  - Order belongs to one Customer. ON DELETE RESTRICT — you must never be
    able to delete a customer who has order history (financial/operational
    record). This differs from default orders, which used CASCADE.
  - Order has many OrderItems. cascade="all, delete-orphan" + lazy="selectin"
    — same parent-child pattern as default orders (replace-all on edit).
  - OrderItem references one Product. ON DELETE RESTRICT — can't delete a
    product referenced by any order line.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.customer import Customer
    from app.models.product import Product


class OrderStatus(str, Enum):
    """Order lifecycle. Forward flow plus cancel-from-anywhere.

    received   — order placed, not yet started
    preparing  — being made (bakery's morning prep, ~6 AM onward)
    ready      — made, awaiting handoff (~8-9 AM)
    delivering — out for delivery / being handed over (~9 AM onward)
    cancelled  — order cancelled (terminal, reachable from any state)
    """

    received = "received"
    preparing = "preparing"
    ready = "ready"
    delivering = "delivering"
    cancelled = "cancelled"


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )

    customer_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("customers.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    status: Mapped[OrderStatus] = mapped_column(
        SAEnum(OrderStatus, name="order_status", native_enum=True),
        nullable=False,
        default=OrderStatus.received,
        index=True,
    )

    # Which day's business this order belongs to. Defaults to today,
    # editable for back-entry. The "today's orders" view filters on this.
    order_date: Mapped[date] = mapped_column(
        Date, nullable=False, default=date.today, index=True
    )

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Stored total, computed from item subtotals at write time (snapshot
    # principle — the total is part of the historical record).
    total_amount: Mapped[float] = mapped_column(
        Numeric(10, 2), nullable=False, default=0
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Parent-child: replace-all on edit via delete-orphan; selectin for the
    # collection (batched second query, no parent-row multiplication).
    items: Mapped[list["OrderItem"]] = relationship(
        "OrderItem",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="OrderItem.created_at",
    )

    # To-one to customer; joined so order displays carry customer name
    # without a second query.
    customer: Mapped["Customer"] = relationship(
        "Customer",
        lazy="joined",
    )


class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )

    order_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    product_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    # --- Snapshotted fields (captured at creation, never change) ---
    product_name: Mapped[str] = mapped_column(String(300), nullable=False)
    unit_price: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    unit_label: Mapped[str] = mapped_column(String(30), nullable=False)
    # --- End snapshot ---

    quantity: Mapped[int] = mapped_column(Integer, nullable=False)

    # unit_price × quantity, stored at write time.
    subtotal: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # To-one to product, joined. Kept for linking/analytics even though
    # display uses the snapshot fields.
    product: Mapped["Product"] = relationship(
        "Product",
        lazy="joined",
    )
