"""Twilio inbound webhook — main dispatcher.

For each inbound WhatsApp message:

  1. Parse the form payload (signature already verified by the dependency).
  2. Strip the 'whatsapp:' prefix from the From address to get a clean
     phone number we match against the database.
  3. Get or create the Conversation row in Postgres (audit trail anchor).
  4. Log the inbound message.
  5. Decide which handler runs:
     - Pending registration in 'pending' or 'rejected' status → registration handler
     - Recognised Customer → customer handler
     - Unknown phone → registration handler (will create the row)
  6. Send the reply via one of two paths:
     - TwiML synchronous (single text reply, e.g. registration flow)
     - REST API (multi-message or template-bearing replies, e.g. any
       customer_handler match that uses bakeriq_* Content Templates)
  7. Log the outbound reply (TwiML path does this here; REST API path
     logs internally inside the sender functions).

LLM safety valve: if the customer handler returns None (no fast-path
match), we hand off to Celery and reply with empty TwiML. The Celery
worker will send the real reply via the REST API once it has the LLM
response.
"""

import logging

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.twilio_client import verify_twilio_signature
from app.services import (
    conversation_log,
    customer_handler,
    registration_handler,
    whatsapp_sender,
)
from app.services import (
    pending_registration_service as pr_svc,
)
from app.services.reply import Reply

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post(
    "/twilio",
    dependencies=[Depends(verify_twilio_signature)],
    response_class=Response,
)
async def twilio_inbound(
    request: Request,
    db: Session = Depends(get_db),
) -> Response:
    """Main inbound dispatcher for WhatsApp messages."""
    form = await request.form()
    body = str(form.get("Body", "")).strip()
    from_address = str(form.get("From", ""))
    twilio_sid = str(form.get("MessageSid", "")) or None

    # Twilio addresses arrive as "whatsapp:+919..." — strip the prefix
    # so we match against the same format we store in Customer.primary_phone.
    phone = from_address.removeprefix("whatsapp:") if from_address else ""

    if not phone:
        logger.warning(
            "Twilio webhook with missing/blank From: form=%s",
            dict(form),
        )
        return _twiml_response("Sorry, I didn't catch that. Please try again.")

    # === Identify the sender ===
    customer = conversation_log.find_customer_by_phone(db, phone)
    pending = pr_svc.get_by_phone(db, phone)

    # === Get or create the conversation ===
    conversation = conversation_log.get_or_create_conversation(
        db,
        phone=phone,
        customer_id=customer.id if customer else None,
    )

    # === Log the inbound ===
    conversation_log.log_inbound_message(
        db,
        conversation_id=conversation.id,
        body=body,
        twilio_sid=twilio_sid,
    )

    # === Dispatch ===
    replies = _dispatch(db, phone, body, customer, pending)

    if replies is None:
        # LLM safety valve takes over. Enqueue the Celery worker —
        # it'll parse, match, write a cart, and send the outbound
        # asynchronously via Twilio's REST API.
        #
        # We commit FIRST so the inbound message + conversation row
        # are visible to the worker (which uses its own session). The
        # outbound from the worker logs itself.
        db.commit()

        from app.tasks.llm import parse_and_send

        # Customer is guaranteed non-None when replies is None — only
        # the customer_handler branch can return None.
        assert customer is not None
        parse_and_send.delay(
            customer_id=str(customer.id),
            conversation_id=str(conversation.id),
            phone=phone,
            body=body,
        )
        # Empty TwiML — Twilio sends nothing in immediate reply, the
        # async send arrives shortly after.
        return _empty_twiml_response()

    # === Pick delivery channel ===
    # Single text reply → TwiML (saves a Twilio API round-trip; still
    # the fast path for the registration flow and any one-shot text
    # responses). Multi-reply or anything carrying a content_sid → REST
    # API, because TwiML can't carry a Content Template.
    if len(replies) == 1 and not replies[0].is_template:
        reply = replies[0]
        assert reply.body is not None
        conversation_log.log_outbound_message(
            db,
            conversation_id=conversation.id,
            body=reply.body,
            twilio_sid=None,
        )
        db.commit()
        return _twiml_response(reply.body)

    # Multi-message or template path: send each via REST API. Sender
    # logs each outbound to conversation_messages internally, so we
    # only need to commit once at the end.
    whatsapp_sender.send_replies(
        db,
        conversation_id=conversation.id,
        to_phone=phone,
        replies=replies,
    )
    db.commit()
    return _empty_twiml_response()


def _empty_twiml_response() -> Response:
    """TwiML response with no message body.

    Used when the reply was already delivered out-of-band (via the REST
    API, either by send_replies in this handler or by the LLM safety
    valve in a Celery worker) — we still have to give Twilio a valid
    TwiML response to the webhook, just one that doesn't include a
    <Message> tag. Twilio accepts this and sends nothing immediately.
    """
    twiml = '<?xml version="1.0" encoding="UTF-8"?>\n<Response></Response>'
    return Response(content=twiml, media_type="application/xml")


def _dispatch(
    db: Session,
    phone: str,
    body: str,
    customer,
    pending,
) -> list[Reply] | None:
    """Pick the right handler and return its reply.

    Returns:
        list[Reply] — handler matched; webhook delivers each reply.
        None       — only when customer_handler had no fast-path match;
                     webhook hands off to LLM safety valve.

    Decision order:
      1. Pending registration in 'awaiting_approval' or 'rejected' status →
         registration_handler (returns list[Reply], typically the webform
         CTA card, or a "still awaiting" text reply).
      2. Customer recognised by phone → customer_handler (returns
         list[Reply] | None; None triggers the LLM safety valve).
      3. Truly unknown phone → registration_handler (issues a fresh
         registration token + returns the webform CTA card).
    """
    # Case 1+2: pending registration (handler covers both 'awaiting_approval' and 'rejected')
    if pending and pending.status in ("awaiting_approval", "rejected"):
        replies = registration_handler.handle_registration_message(db, phone, body)
        return replies

    # Case 3: known customer → fast-path or LLM
    if customer:
        replies = customer_handler.handle_customer_message(db, customer, body)
        if replies is None:
            # Hand-off point to LLM safety valve. Returning None tells
            # the caller to enqueue the Celery task and send empty
            # TwiML — the LLM worker will deliver the real reply
            # asynchronously via Twilio's REST API.
            logger.info(
                "LLM safety-valve hit: customer_id=%s phone=%s body=%r",
                customer.id,
                phone,
                body,
            )
            return None
        return replies

    # Case 4: truly unknown phone → start registration
    replies = registration_handler.handle_registration_message(db, phone, body)
    return replies


def _twiml_response(message: str) -> Response:
    """Wrap a reply string in TwiML XML for the synchronous Twilio reply.

    XML-escapes the body so customer-influenced data can't break the
    response (e.g., a customer name containing '&' or '<').
    """
    from xml.sax.saxutils import escape

    twiml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        "<Response>\n"
        f"  <Message>{escape(message)}</Message>\n"
        "</Response>"
    )
    return Response(content=twiml, media_type="application/xml")
