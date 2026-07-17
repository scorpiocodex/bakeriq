"""RegistrationToken — one-time credential for the registration webform.

When a phone number the bot doesn't recognise sends a message, we issue
a RegistrationToken and send back a WhatsApp Content Template card
with a CTA button. The button URL is https://<ngrok>/web/register/{token},
which loads a webform pre-filled with the phone number.

The token is:
  - Bound to a specific phone (proven by WhatsApp delivering it)
  - Valid for 12 hours from issue
  - One-time-use: after the customer POSTs the form, we mark it consumed
  - Deletable independently of any customer records (a rejected
    registration should still allow re-issuance later)

Design decisions:

  - Separate table (not extending WebLink). WebLink is customer-bound
    (`customer_id NOT NULL`); registration happens BEFORE a customer
    exists. Making WebLink's customer_id nullable to accommodate both
    would risk silent bugs in the well-tested cart flow. Two tables
    with clean semantics beats one polymorphic table.

  - `consumed_at` timestamp rather than `is_consumed` boolean. Same
    reasoning as WebLink — audit trail: "when was this consumed" is
    more useful for debugging than "is it consumed."

  - `phone` (not `phone_number`) to match the naming in Conversation
    and PendingRegistration tables. Consistency > uniformity with a
    different table's convention.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import DateTime, String
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

if TYPE_CHECKING:
    pass


class RegistrationToken(Base):
    __tablename__ = "registration_tokens"

    id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid4
    )

    # The phone number this token was issued to. The webform pre-fills
    # this in the phone field and does NOT accept overrides — the token
    # binds the registration to this specific phone.
    phone: Mapped[str] = mapped_column(String(24), index=True, nullable=False)

    # URL-safe random token — the string that appears in the webform URL
    # (/web/register/{token}). NOT the id — id is UUID for foreign-key
    # ergonomics; token is the string customers actually paste/tap.
    token: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, nullable=False
    )

    # Set when the customer successfully POSTs the form. Once set, the
    # token cannot be reused; a second POST returns 410 Gone.
    consumed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Standard lifecycle timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    def __repr__(self) -> str:
        state = "consumed" if self.consumed_at else "active"
        return (
            f"<RegistrationToken id={self.id} phone={self.phone} "
            f"token={self.token[:8]}... {state}>"
        )
