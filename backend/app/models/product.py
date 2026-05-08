"""Product model — what the bakery sells.

Schema notes:
  - Single-unit-per-product design. A bakery item sold in two configurations
    (e.g. ladoo as piece + ladoo as packet of 25) becomes two separate
    product rows. Inventory pooling between them is deferred to Phase 5.
  - category_id: foreign key to the categories table. Owner picks an
    existing category from a dropdown (or creates a new one inline)
    when adding/editing a product. ON DELETE RESTRICT means a category
    can't be hard-deleted while any product references it; soft-delete
    via is_active=false instead.
  - unit_price as NUMERIC(10,2) — money is never floating-point.
  - aliases as JSONB array — read 100% of the time alongside the product
    by the LLM parser (Phase 3); stored inline rather than in a separate
    aliases table because they're never queried independently.
  - is_available_today: owner toggles daily as the bakery's actual menu
    changes. Bot's menu generator filters on this.
  - Soft-delete via is_active — preserves order history references.
"""

from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from app.models.base import Base
from sqlalchemy import Boolean, DateTime, ForeignKey, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship


class Product(Base):
    __tablename__ = "products"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )

    name: Mapped[str] = mapped_column(String(300), nullable=False)

    category_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("categories.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    category: Mapped["Category"] = relationship(  # noqa: F821
        "Category",
        lazy="joined",  # always JOIN — we always want category info with products
    )

    unit_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)

    unit_label: Mapped[str] = mapped_column(String(30), nullable=False, default="piece")

    is_available_today: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )

    aliases: Mapped[list] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default="[]",
    )

    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, index=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
