"""Pending Registration service — owner-approval workflow for new customers.

When an unknown phone first messages the bot, we don't immediately create
a Customer row. Instead:

  1. PendingRegistration created (status='pending', conversation_state
     tracks where we are in the data-collection flow)
  2. Bot collects name → area through 2 message turns
  3. Bot tells customer "owner will approve shortly"
  4. Owner approves in dashboard → real Customer row created here,
     linked via PendingRegistration.customer_id, status flips to 'approved'

This module owns the data layer for that workflow. The bot's actual
message-handler logic lives in registration_handler.py.
"""

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.customer import Customer
from app.models.pending_registration import PendingRegistration


# Sub-states within the registration flow itself. Distinct from the Redis
# conversation_state which is broader (covers ordering too).
SUBSTATE_COLLECTING_NAME = "collecting_name"
SUBSTATE_COLLECTING_AREA = "collecting_area"
SUBSTATE_AWAITING_APPROVAL = "awaiting_approval"


def get_pending_by_phone(db: Session, phone: str) -> PendingRegistration | None:
    """Return the pending registration row for a phone, if any. None otherwise.

    Used by the webhook dispatcher to decide "is this an in-progress
    registration?" before falling back to "is this a registered customer?"
    """
    return db.scalar(
        select(PendingRegistration).where(PendingRegistration.phone == phone)
    )


def start_registration(db: Session, phone: str) -> PendingRegistration:
    """Create a fresh pending_registration row for a previously-unknown phone.

    The substate starts at collecting_name — the bot's next reply will
    ask for the customer's name.

    Raises an error if a row already exists. The caller is expected to
    have checked first (via get_pending_by_phone).
    """
    existing = get_pending_by_phone(db, phone)
    if existing is not None:
        raise ValueError(
            f"Pending registration already exists for phone {phone}; "
            f"resume it instead of starting a new one."
        )

    reg = PendingRegistration(
        phone=phone,
        conversation_state=SUBSTATE_COLLECTING_NAME,
        status="pending",
    )
    db.add(reg)
    db.flush()
    return reg


def record_name(db: Session, reg: PendingRegistration, name: str) -> None:
    """Save the customer's name and advance to the next substate."""
    reg.name = name.strip()[:120]
    reg.conversation_state = SUBSTATE_COLLECTING_AREA
    db.flush()


def record_area(db: Session, reg: PendingRegistration, area: str) -> None:
    """Save the customer's area and advance to awaiting-approval substate."""
    reg.area = area.strip()[:200]
    reg.conversation_state = SUBSTATE_AWAITING_APPROVAL
    db.flush()


def approve(
    db: Session,
    reg: PendingRegistration,
) -> Customer:
    """Owner approval path — converts pending_registration into a real Customer.

    Called by the dashboard approval endpoint (Task 8). NOT called from
    the bot handler directly.

    Creates a Customer row with the collected name + phone, marks the
    pending row as approved, and links them via customer_id. The bot's
    next interaction with this customer will recognise them as registered.
    """
    if reg.status != "pending":
        raise ValueError(f"Cannot approve registration in status {reg.status!r}")
    if not reg.name or not reg.area:
        raise ValueError(
            "Registration is incomplete; name and area must be provided "
            "before approval."
        )

    # Build the Customer row from what we've collected. The 'area' isn't
    # a real address (more like a neighbourhood label — "MG Road", "Kakkanad")
    # so it goes into notes. The owner fills in the proper address fields
    # via the dashboard when they need to deliver — those fields are
    # nullable specifically to support this two-stage flow.
    customer = Customer(
        name=reg.name,
        primary_phone=reg.phone,
        whatsapp_enabled=True,
        notes=f"Auto-registered via WhatsApp. Area: {reg.area}",
        is_active=True,
    )
    db.add(customer)
    db.flush()  # Need the customer.id for the link below

    reg.status = "approved"
    reg.customer_id = customer.id
    reg.approved_at = datetime.now(timezone.utc)
    db.flush()

    return customer


def reject(db: Session, reg: PendingRegistration) -> None:
    """Owner rejection path — marks as rejected. Row stays for record.

    No customer is created. The bot's next interaction with this phone
    will... currently treat them as a new unknown, which would restart
    registration. We'll need to gate that in the bot handler — if a
    rejected registration exists, the bot should politely decline rather
    than restart. (Task 3 substep 4 will handle this.)
    """
    if reg.status != "pending":
        raise ValueError(f"Cannot reject registration in status {reg.status!r}")
    reg.status = "rejected"
    db.flush()


def list_pending(
    db: Session,
    *,
    skip: int = 0,
    limit: int = 50,
) -> tuple[list[PendingRegistration], int]:
    """Pending registrations awaiting owner action.

    Returns (rows, total_count). Status='pending' only — rejected and
    approved rows aren't in the queue.

    Sorted oldest-first so the owner naturally clears the queue in FIFO
    order.
    """
    from sqlalchemy import func

    base_q = select(PendingRegistration).where(
        PendingRegistration.status == "pending"
    )

    rows = db.scalars(
        base_q.order_by(PendingRegistration.created_at.asc())
        .offset(skip)
        .limit(limit)
    ).all()

    total = db.scalar(
        select(func.count(PendingRegistration.id))
        .where(PendingRegistration.status == "pending")
    ) or 0

    return list(rows), total
