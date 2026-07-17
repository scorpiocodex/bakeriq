"""PendingRegistration service — CRUD + approve/reject helpers.

Post-Phase 3.5 refactor: the bot state machine is gone. Pending rows
are created directly from the webform submission (see
registration_form_service) and moved through owner action from the
approvals dashboard.

Status values:
  - 'awaiting_approval'  — created by the webform, waiting on owner
  - 'approved'           — owner approved, Customer row created
  - 'rejected'           — owner rejected, no Customer created

The row is retained for audit in both terminal states.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.customer import Customer
from app.models.pending_registration import PendingRegistration

STATUS_AWAITING = "awaiting_approval"
STATUS_APPROVED = "approved"
STATUS_REJECTED = "rejected"


def get_by_phone(db: Session, phone: str) -> PendingRegistration | None:
    """Latest PendingRegistration row for a phone number.

    'Latest' because a phone that was rejected could theoretically
    submit a new registration; the newer row is the relevant one for
    the current interaction.
    """
    return db.scalar(
        select(PendingRegistration)
        .where(PendingRegistration.phone == phone)
        .order_by(PendingRegistration.created_at.desc())
        .limit(1)
    )


def get_awaiting_by_phone(db: Session, phone: str) -> PendingRegistration | None:
    """Awaiting-approval row for a phone, or None.

    Used to answer "does this phone have a registration in flight?"
    without dragging in old rejected rows.
    """
    return db.scalar(
        select(PendingRegistration).where(
            PendingRegistration.phone == phone,
            PendingRegistration.status == STATUS_AWAITING,
        )
    )


def create_from_webform(
    db: Session,
    *,
    phone: str,
    name: str,
    address_line_1: str | None = None,
    address_line_2: str | None = None,
    city: str | None = None,
    state: str | None = None,
    pincode: str | None = None,
) -> PendingRegistration:
    """Create a new pending registration directly from a webform submission.

    Called by registration_form_service after the customer submits the
    form. Status is set to 'awaiting_approval' immediately — there's
    no intermediate state because the webform collected everything in
    one shot.

    The caller (form service) is responsible for validating the token
    and preventing duplicate submissions.
    """
    reg = PendingRegistration(
        phone=phone,
        name=name.strip()[:100],
        address_line_1=(address_line_1 or "").strip()[:200] or None,
        address_line_2=(address_line_2 or "").strip()[:200] or None,
        city=(city or "").strip()[:100] or None,
        state=(state or "").strip()[:100] or None,
        pincode=(pincode or "").strip()[:10] or None,
        status=STATUS_AWAITING,
    )
    db.add(reg)
    db.flush()
    return reg


def approve(db: Session, reg: PendingRegistration) -> Customer:
    """Owner approval path — creates the Customer row and links it.

    Called by the /approvals dashboard endpoint. Field-copies the
    registration data into a new Customer row and marks the pending
    row as approved.

    The address fields map 1:1 into Customer (both models share the
    same shape). notes gets a "how they joined" trail so the origin
    is visible in the admin UI later.
    """
    if reg.status != STATUS_AWAITING:
        raise ValueError(f"Cannot approve registration in status {reg.status!r}")
    if not reg.name:
        raise ValueError(
            "Registration is incomplete; name must be provided before approval."
        )

    customer = Customer(
        name=reg.name,
        primary_phone=reg.phone,
        whatsapp_enabled=True,
        address_line_1=reg.address_line_1,
        address_line_2=reg.address_line_2,
        city=reg.city,
        state=reg.state,
        pincode=reg.pincode,
        notes="Auto-registered via WhatsApp webform",
        is_active=True,
    )
    db.add(customer)
    db.flush()

    reg.status = STATUS_APPROVED
    reg.customer_id = customer.id
    reg.approved_at = datetime.now(timezone.utc)
    db.flush()

    return customer


def reject(db: Session, reg: PendingRegistration) -> None:
    """Owner rejection path — marks as rejected, no Customer created.

    Rejected registrations stay in the table for audit. If the same
    phone attempts a fresh registration later, the bot handler
    (registration_handler) sees the rejected row via get_by_phone
    and can decide how to respond (currently: politely decline).
    """
    if reg.status != STATUS_AWAITING:
        raise ValueError(f"Cannot reject registration in status {reg.status!r}")
    reg.status = STATUS_REJECTED
    db.flush()


def list_awaiting(
    db: Session,
    *,
    skip: int = 0,
    limit: int = 50,
) -> tuple[list[PendingRegistration], int]:
    """Registrations awaiting owner action, oldest-first.

    Returns (rows, total_count). Only 'awaiting_approval' — rejected
    and approved rows aren't in the queue.

    FIFO order because the owner should clear older requests first;
    a customer waiting 6 hours shouldn't be behind one that came in
    10 minutes ago.
    """
    base_q = select(PendingRegistration).where(
        PendingRegistration.status == STATUS_AWAITING
    )
    rows = db.scalars(
        base_q.order_by(PendingRegistration.created_at.asc()).offset(skip).limit(limit)
    ).all()
    total = (
        db.scalar(
            select(func.count(PendingRegistration.id)).where(
                PendingRegistration.status == STATUS_AWAITING
            )
        )
        or 0
    )
    return list(rows), total


def count_awaiting(db: Session) -> int:
    """Count of pending registrations — used by the sidebar badge."""
    return (
        db.scalar(
            select(func.count(PendingRegistration.id)).where(
                PendingRegistration.status == STATUS_AWAITING
            )
        )
        or 0
    )
