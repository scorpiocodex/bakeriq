"""Customer model — the bakery's customer list.

Schema notes:
  - Two phone columns (primary + secondary) with cross-column uniqueness
    enforced at the application layer (see customer_service.py).
  - Indian-postal-format address: 5 columns. All are nullable at the DB
    layer (Pydantic enforces address-required for dashboard creates;
    bot-registered customers can have nullable address fields until the
    owner fills them in).
  - pincode is VARCHAR(6) with a regex check at the Pydantic layer
    (^\\d{6}$). DB stores as string to preserve any formatting nuances and
    avoid silent integer-coercion issues.
  - Soft-delete pattern via is_active. We never DELETE customer rows
    because future orders will FK to them.
"""
from datetime import datetime
from enum import Enum as PyEnum
from uuid import uuid4, UUID

from sqlalchemy import String, Boolean, DateTime, Text, Enum as SAEnum, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class PreferredPhone(PyEnum):
    """Which of the two phones the bot should try first.

    Pydantic v2 with use_enum_values handles serialisation; no need
    for the str-mixin pattern that breaks SAEnum's introspection.
    """
    PRIMARY = "primary"
    SECONDARY = "secondary"


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    # === Phones ===
    primary_phone: Mapped[str] = mapped_column(
        String(20),
        unique=True,
        index=True,
        nullable=False,
    )
    secondary_phone: Mapped[str | None] = mapped_column(
        String(20),
        unique=True,
        nullable=True,
    )
    preferred_channel_phone: Mapped[PreferredPhone] = mapped_column(
        SAEnum(
            PreferredPhone,
            name="preferred_phone",
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
        default=PreferredPhone.PRIMARY,
    )

    whatsapp_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )

    # === Address — Indian postal format ===
    # All address fields are nullable at the DB layer because customers
    # can be created via two paths:
    #   1. Dashboard create (manual entry by owner) — Pydantic layer
    #      requires address_line_1, city, state, pincode.
    #   2. Bot registration (WhatsApp) — collects only name + area.
    #      The 'area' is recorded in the notes field; full address is
    #      filled in via the dashboard later when delivery is needed.
    # address_line_2 has always been optional (e.g. only used for
    # post office / locality / secondary landmark).
    # pincode stored as VARCHAR(6) not INTEGER to preserve format and
    # prevent integer-coercion silently dropping leading zeros.
    address_line_1: Mapped[str | None] = mapped_column(String(255), nullable=True)
    address_line_2: Mapped[str | None] = mapped_column(String(255), nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    state: Mapped[str | None] = mapped_column(String(100), nullable=True)
    pincode: Mapped[str | None] = mapped_column(String(6), nullable=True)

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
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
