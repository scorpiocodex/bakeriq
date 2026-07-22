"""Owner notification service — sends a WhatsApp card to the bakery owner
when something needs their attention.

Currently one trigger: new pending registration via the webform. The
customer's submission succeeds regardless of whether the notification
lands; failures here are logged and swallowed. If Twilio is down or
credentials broke, the owner still sees the queue via the dashboard
badge polling.

Owner phone is configured via OWNER_WHATSAPP_PHONE in .env. If unset,
notification is a no-op (with a warning log). Useful for local dev
without a real owner phone.
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.core.config import settings
from app.services import conversation_log, whatsapp_sender
from app.services.template_replies import owner_registration_notification_reply

logger = logging.getLogger(__name__)


def notify_new_registration(db: Session, *, name: str, phone: str) -> None:
    """Send the owner a WhatsApp card announcing a new registration.

    Called from the /register/{token} POST endpoint after PendingRegistration
    is created and the token consumed.

    Fail semantics: never raises. Twilio errors, missing config, etc.
    all log-and-continue. The registration itself is already committed
    before we reach here; the notification is a nice-to-have.
    """
    owner_phone = settings.OWNER_WHATSAPP_PHONE
    if not owner_phone:
        logger.warning(
            "notify_new_registration: OWNER_WHATSAPP_PHONE not set — "
            "notification skipped (name=%r phone=%r)",
            name,
            phone,
        )
        return

    # Normalise the owner phone the same way the webhook does — strip
    # the 'whatsapp:' prefix if present so the conversation_log call
    # sees a plain phone number.
    owner_phone_plain = owner_phone.replace("whatsapp:", "").strip()

    try:
        # Use the owner's own conversation for audit logging. The owner
        # may not have a Customer row (they're a User, not a Customer),
        # so we get_or_create by phone only, without customer_id.
        conversation = conversation_log.get_or_create_conversation(
            db,
            phone=owner_phone_plain,
            customer_id=None,
        )

        reply = owner_registration_notification_reply(name=name, phone=phone)

        sids = whatsapp_sender.send_replies(
            db,
            conversation_id=conversation.id,
            to_phone=owner_phone_plain,
            replies=[reply],
        )

        if any(sid is None for sid in sids):
            logger.warning(
                "notify_new_registration: send returned None SID "
                "(name=%r phone=%r) — owner may not receive card",
                name,
                phone,
            )
        else:
            logger.info(
                "notify_new_registration: sent to owner %s "
                "(new: name=%r phone=%r) sids=%s",
                owner_phone_plain,
                name,
                phone,
                sids,
            )

        db.commit()
    except Exception as e:
        # Broad except: any failure here must not fail the caller.
        # We already committed the registration; the customer got their
        # success response. Notification is best-effort.
        logger.exception("notify_new_registration: exception sending to owner: %s", e)
        db.rollback()
