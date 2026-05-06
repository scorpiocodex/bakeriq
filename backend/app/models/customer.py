"""Customer model — the bakery's customer list."""

from datetime import datetime
from enum import Enum as PyEnum
from uuid import UUID, uuid4

from app.models.base import Base
from sqlalchemy import Boolean, DateTime
from sqlalchemy import Enum as SAEnum
from sqlalchemy import String, Text, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column


class PreferredPhone(str, PyEnum):
    """Which of the two phones the bot should try first.

    str-based PyEnum so the values serialise to their string form
    automatically in JSON responses. Postgres stores them as native
    ENUM; SQLAlchemy handles the conversion both ways.
    """

    PRIMARY = "primary"
    SECONDARY = "secondary"


class Customer(Base):
    """Customer model"""

    __tablename__ = "customers"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
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
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
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
