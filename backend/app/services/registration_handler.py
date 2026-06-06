"""Registration handler — bot logic for the new-customer onboarding flow.

Entry point: handle_registration_message(db, phone, body) returns a
reply string. Caller (the webhook dispatcher) sends that reply to the
customer via TwiML or the REST API.

Three sub-states drive the conversation:

  collecting_name      — bot's last reply asked for the customer's name.
                         Any text from the customer is treated as their
                         name and stored. Reply asks for area.

  collecting_area      — bot's last reply asked for the area. Any text
                         is treated as their area. Reply tells them to
                         wait for owner approval.

  awaiting_approval    — bot already said "wait for approval". Any
                         further messages get a polite "still waiting"
                         reply. The owner approving them in the dashboard
                         is what flips state — not anything the customer
                         does here.

Edge cases:
  - "rejected" status:  customer was rejected previously. Bot politely
                        says "we can't accept your registration; please
                        contact the bakery directly."
  - "approved" status:  customer is registered but somehow still in a
                        registering state (shouldn't happen — defensive
                        only). Bot acknowledges and clears state, so
                        next message goes through the normal returning-
                        customer path.
"""

from sqlalchemy.orm import Session

from app.models.pending_registration import PendingRegistration
from app.services import pending_registration_service as pr_svc

# Outbound message templates. Kept as constants here so they're easy to
# tune copy without hunting through logic. WhatsApp supports * for *bold*
# and _italic_; we use * for emphasis sparingly.
MSG_GREETING_NEW = (
    "Welcome to BakeriQ!\n"
    "\n"
    "I don't recognise this number yet. To place orders, I just need "
    "a couple of details.\n"
    "\n"
    "*What's your full name?*"
)

MSG_ASK_AREA = (
    "Thanks {name}!\n"
    "\n"
    "*Which area are you ordering for?* "
    "(e.g. MG Road, Kochi)"
)

MSG_AWAITING_APPROVAL = (
    "Got it. I've shared your details with the bakery owner for approval.\n"
    "\n"
    "I'll message you here once you're approved — usually within an hour."
)

MSG_STILL_AWAITING = (
    "Your registration is still being reviewed by the bakery owner. "
    "I'll let you know as soon as you're approved."
)

MSG_REJECTED = (
    "I'm sorry, the bakery owner wasn't able to approve your registration. "
    "Please contact the bakery directly if you'd like to discuss this."
)


def handle_registration_message(
    db: Session,
    phone: str,
    body: str,
) -> str:
    """Drive the registration sub-state machine. Returns the bot's reply.

    This function does NOT send the reply — it just returns the text.
    The caller sends via TwiML or REST.
    """
    reg = pr_svc.get_pending_by_phone(db, phone)

    # No existing registration → first contact. Create the row and ask
    # for name.
    if reg is None:
        pr_svc.start_registration(db, phone)
        return MSG_GREETING_NEW

    # Existing registration — dispatch by status + substate
    if reg.status == "rejected":
        return MSG_REJECTED

    if reg.status == "approved":
        # Shouldn't happen — if approved, the dispatcher should have
        # matched them as a registered customer instead. Defensive
        # fallback: tell them we recognise them and let next round work
        # via the normal customer path. We don't clear the row.
        return (
            "Welcome back! Send 'order' to place an order, "
            "or 'menu' to see today's items."
        )

    # status == 'pending' from here on. Dispatch by substate.
    if reg.conversation_state == pr_svc.SUBSTATE_COLLECTING_NAME:
        return _handle_collect_name(db, reg, body)

    if reg.conversation_state == pr_svc.SUBSTATE_COLLECTING_AREA:
        return _handle_collect_area(db, reg, body)

    if reg.conversation_state == pr_svc.SUBSTATE_AWAITING_APPROVAL:
        return MSG_STILL_AWAITING

    # Unknown substate — defensive fallback. Reset to collecting_name.
    reg.conversation_state = pr_svc.SUBSTATE_COLLECTING_NAME
    db.flush()
    return MSG_GREETING_NEW


def _handle_collect_name(
    db: Session,
    reg: PendingRegistration,
    body: str,
) -> str:
    """Customer's response should be their name. Save it, ask for area."""
    name = body.strip()
    if not name:
        # Empty message in this state — re-prompt
        return MSG_GREETING_NEW

    pr_svc.record_name(db, reg, name)
    # Use only the first word of the name for friendlier follow-up
    first_name = name.split()[0]
    return MSG_ASK_AREA.format(name=first_name)


def _handle_collect_area(
    db: Session,
    reg: PendingRegistration,
    body: str,
) -> str:
    """Customer's response should be their area. Save it, await approval."""
    area = body.strip()
    if not area:
        return MSG_ASK_AREA.format(name=(reg.name or "there").split()[0])

    pr_svc.record_area(db, reg, area)
    return MSG_AWAITING_APPROVAL
