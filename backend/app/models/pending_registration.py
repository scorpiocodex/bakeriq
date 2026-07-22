"""PendingRegistration — a customer trying to become a Customer.

Created by the registration webform when a phone that isn't yet a
Customer submits their details. Sits in `awaiting_approval` state
until the bakery owner either approves it (promotes to Customer) or
rejects it (marks rejected, out).

Fields mirror the Customer schema so the approval flow is a clean
1:1 field copy — no re-parsing needed on the owner's side.

State machine (post-Phase 3.5 refactor):
  - Row is created directly with status='awaiting_approval'.
  - Owner action → status transitions to 'approved' or 'rejected'.
  - No 'collecting_*' states anymore — the old bot conversation flow
    was replaced by the webform. See git history for the deleted
    state machine if you're archaeology-curious.

Approved rows are kept for audit — customer_id is set to the created
Customer's id, and the row functions as "how this Customer joined."
Rejected rows are kept too; they're rare enough that the storage
cost doesn't matter, and they help the owner see who was declined
if the customer comes back and asks.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.customer import Customer


class PendingRegistration(Base):
    __tablename__ = "pending_registrations"

    id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid4
    )

    # The phone that this registration attempt is for.
    phone: Mapped[str] = mapped_column(String(24), index=True, nullable=False)

    # Customer details supplied via the webform.
    name: Mapped[str] = mapped_column(String(100), nullable=False)

    # Structured address fields matching the Customer table so approval
    # is a straight column-for-column copy.
    address_line_1: Mapped[str | None] = mapped_column(String(200), nullable=True)
    address_line_2: Mapped[str | None] = mapped_column(String(200), nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    state: Mapped[str | None] = mapped_column(String(100), nullable=True)
    pincode: Mapped[str | None] = mapped_column(String(10), nullable=True)

    # Lifecycle status.
    # Values: 'awaiting_approval' | 'approved' | 'rejected'
    # (No enum type — keeps migrations simple. String comparison is
    # cheap and lookups are indexed.)
    status: Mapped[str] = mapped_column(
        String(30), index=True, nullable=False, default="awaiting_approval"
    )

    # Populated on approval: the newly-created Customer's id.
    # Null for pending and rejected rows.
    customer_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("customers.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationship
    customer: Mapped["Customer | None"] = relationship(
        "Customer", foreign_keys=[customer_id]
    )

    def __repr__(self) -> str:
        return (
            f"<PendingRegistration id={self.id} phone={self.phone} "
            f"name={self.name!r} status={self.status}>"
        )
