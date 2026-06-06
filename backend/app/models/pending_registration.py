"""Pending Registration model — unknown WhatsApp phones awaiting owner approval.

Workflow:
  1. Unknown phone messages the bot.
  2. Bot collects name + area through 2-3 message turns.
  3. Row is created here with status='pending'.
  4. Owner sees it in the dashboard and approves or rejects.
  5. On approval, a real Customer row is created and `customer_id` is set
     here for the audit trail. Status flips to 'approved'.
  6. On rejection, status flips to 'rejected'. Row stays as record.

The `conversation_state` field tracks where we are in the registration
flow itself (collecting_name → collecting_area → awaiting_approval).
This is distinct from the Redis conversation state used for ordering.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from app.models.base import Base
from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

if TYPE_CHECKING:
    from app.models.customer import Customer


class PendingRegistration(Base):
    __tablename__ = "pending_registrations"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )

    # Phone number is the natural key — one pending registration per phone.
    # If a customer tries to re-register, we reuse the existing row.
    phone: Mapped[str] = mapped_column(
        String(20), nullable=False, unique=True, index=True
    )

    name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    area: Mapped[str | None] = mapped_column(String(200), nullable=True)

    # Sub-state within the registration flow itself. Distinct from the
    # Redis-side conversation state for ordering.
    conversation_state: Mapped[str] = mapped_column(
        String(40), nullable=False, default="collecting_name"
    )

    # status enum (kept as a String column for simplicity — owner only ever
    # sees three values; not worth a native Postgres enum):
    #   pending     — created, awaiting owner action
    #   approved    — owner approved; Customer row exists at customer_id
    #   rejected    — owner rejected; row stays for record
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending", index=True
    )

    customer_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("customers.id", ondelete="SET NULL"),
        nullable=True,
    )

    customer: Mapped["Customer | None"] = relationship(
        "Customer",
        lazy="joined",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
