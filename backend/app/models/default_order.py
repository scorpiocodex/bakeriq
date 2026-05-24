"""Default Order models — a customer's recurring order template.

Concept:
  A default order is a *recipe*, not a real order. It captures "what this
  customer usually wants" so the WhatsApp bot (Phase 3) can draft a daily
  message ("Hi Anita, your usual 5 puffs and 1 packet of biscuits — confirm?").
  When confirmed, a real Order (Phase 2 task 4) gets created FROM this
  template.
"""

from datetime import datetime
from uuid import UUID, uuid4

from app.models.base import Base
from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship


class DefaultOrder(Base):
    __tablename__ = "default_orders"
    __table_args__ = (
        # One template per customer. The unique constraint is named so
        # future migrations can reference it cleanly.
        UniqueConstraint("customer_id", name="uq_default_orders_customer_id"),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )

    customer_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("customers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Optional free-text notes — "skip Sundays", "double on Fridays", etc.
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Soft-disable without deleting — owner can pause a template.
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, index=True
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

    # Relationship to the child items. cascade="all, delete-orphan" is the
    # key to the replace-all update pattern: when we reassign .items to a
    # new list, orphaned old items are deleted automatically.
    # lazy="selectin" loads all items in a second batched query (efficient
    # for collections — avoids the N+1 problem without a JOIN that would
    # multiply parent rows).
    items: Mapped[list["DefaultOrderItem"]] = relationship(
        "DefaultOrderItem",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="DefaultOrderItem.created_at",
    )


class DefaultOrderItem(Base):
    __tablename__ = "default_order_items"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )

    default_order_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("default_orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    product_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    quantity: Mapped[int] = mapped_column(Integer, nullable=False)

    # Relationship to the product — lazy="joined" so when we serialise an
    # item we have its product details (name, price) without a separate
    # query. Same pattern as Product.category.
    product: Mapped["Product"] = relationship(  # noqa: F821
        "Product",
        lazy="joined",
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
