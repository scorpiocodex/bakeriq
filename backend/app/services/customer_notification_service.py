"""Customer notification service — outbound alerts to customers.

Currently one trigger: the owner approving a registration. The webform
tells the customer "you'll get a WhatsApp message once the bakery owner
approves you", and the bot's awaiting-approval reply says "I'll let you
know as soon as you're approved" — this is what makes both true.

Mirrors owner_notification_service in shape and fail semantics: sync,
best-effort, never raises. The approval itself is already committed by
the time we get here, so a Twilio failure must not undo it. The customer
finds out either way the next time they message the bot, which now
recognises them.

Rejection deliberately doesn't notify. Neither the form nor the bot
promised a message in that case, and an unprompted "you've been turned
down" is a worse experience than the polite decline the bot already
gives if they message again.
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.models.customer import Customer
from app.services import conversation_log, whatsapp_sender
from app.services.template_replies import approved_reply

logger = logging.getLogger(__name__)


def notify_approved(db: Session, customer: Customer) -> None:
    """Tell a newly approved customer they can start ordering.

    Called from the approvals endpoint after the Customer row is
    committed. Never raises — see the module docstring.
    """
    try:
        conversation = conversation_log.get_or_create_conversation(
            db,
            phone=customer.primary_phone,
            customer_id=customer.id,
        )

        reply = approved_reply(customer.name)

        sids = whatsapp_sender.send_replies(
            db,
            conversation_id=conversation.id,
            to_phone=customer.primary_phone,
            replies=[reply],
        )

        if any(sid is None for sid in sids):
            logger.warning(
                "notify_approved: send returned None SID for customer=%s — "
                "they may not have received the welcome",
                customer.id,
            )
        else:
            logger.info(
                "notify_approved: sent to %s (customer=%s)",
                customer.primary_phone,
                customer.id,
            )

        db.commit()
    except Exception as e:
        # Broad except: the approval is already committed and must stand.
        logger.exception(
            "notify_approved: exception sending to customer %s: %s",
            customer.id,
            e,
        )
        db.rollback()
