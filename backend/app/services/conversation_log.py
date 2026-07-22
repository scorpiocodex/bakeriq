"""Conversation log service — write inbound/outbound messages to Postgres.

The `conversations` table is one row per long-running customer thread.
The `conversation_messages` table is one row per inbound or outbound
message. Together they're the bot's permanent audit trail — useful for:

  - Debugging customer reports ("the bot said the wrong thing")
  - The dashboard's conversation viewer (Task 9)
  - LLM context (the safety valve can include recent history)

Conversation lifecycle:
  - First inbound from a phone → new Conversation row created
  - Subsequent messages reference the same Conversation
  - There's no "end" — conversations stay open indefinitely; the Redis
    state expires after 30 min but the Postgres history is permanent

We never delete a conversation. Deleting a customer cascades to their
conversation via the FK, but operationally we'd soft-delete the customer
instead.
"""

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.conversation import Conversation, ConversationMessage
from app.models.customer import Customer


def get_or_create_conversation(
    db: Session,
    *,
    phone: str,
    customer_id: UUID | None = None,
) -> Conversation:
    """Get the active conversation for a phone, or create one if none exists.

    A phone has at most one open conversation. "Open" isn't tracked
    explicitly — we just always look up by phone and reuse the row.

    If customer_id is provided and the existing conversation doesn't have
    one (e.g. it was created during pending registration before approval),
    we update it. Otherwise the existing customer_id is preserved.
    """
    conv = db.scalar(
        select(Conversation).where(Conversation.phone == phone)
    )
    if conv is None:
        conv = Conversation(phone=phone, customer_id=customer_id)
        db.add(conv)
        db.flush()
        return conv

    # Backfill customer_id if we now know who they are
    if customer_id is not None and conv.customer_id is None:
        conv.customer_id = customer_id
        db.flush()

    return conv


def log_inbound_message(
    db: Session,
    *,
    conversation_id: UUID,
    body: str,
    twilio_sid: str | None = None,
    intent: str | None = None,
) -> ConversationMessage:
    """Record an inbound message (from customer to bot).

    intent: set only by the LLM safety-valve path (Task 6). Fast-path
    handlers leave it None — distinguishing "this was a known keyword"
    from "this needed the LLM" is useful for cost analysis later.
    """
    msg = ConversationMessage(
        conversation_id=conversation_id,
        direction="inbound",
        body=body,
        twilio_sid=twilio_sid,
        intent=intent,
    )
    db.add(msg)
    _touch_conversation_timestamp(db, conversation_id)
    db.flush()
    return msg


def log_outbound_message(
    db: Session,
    *,
    conversation_id: UUID,
    body: str,
    twilio_sid: str | None = None,
) -> ConversationMessage:
    """Record an outbound message (from bot to customer).

    twilio_sid may be None if the Twilio API call failed — the audit
    record still gets written so we have evidence of the attempt.
    """
    msg = ConversationMessage(
        conversation_id=conversation_id,
        direction="outbound",
        body=body,
        twilio_sid=twilio_sid,
    )
    db.add(msg)
    _touch_conversation_timestamp(db, conversation_id)
    db.flush()
    return msg


def _touch_conversation_timestamp(db: Session, conversation_id: UUID) -> None:
    """Update last_message_at on the conversation row.

    Used by the conversation list UI to sort "most recently active first".
    We do this explicitly rather than relying on SQLAlchemy's onupdate,
    because onupdate only fires when other fields change.
    """
    conv = db.get(Conversation, conversation_id)
    if conv is not None:
        conv.last_message_at = datetime.now(timezone.utc)


def find_customer_by_phone(db: Session, phone: str) -> Customer | None:
    """Look up a customer by their primary phone. Returns None if no match.

    Used early in webhook dispatch to decide "registered customer vs
    unknown caller." Matches against primary_phone only — secondary
    phones aren't valid for bot identification (the customer's WhatsApp
    is tied to one number).
    """
    return db.scalar(
        select(Customer)
        .where(Customer.primary_phone == phone)
        .where(Customer.is_active.is_(True))
    )
