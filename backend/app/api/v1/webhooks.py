"""Twilio inbound webhook — main dispatcher.

For each inbound WhatsApp message:

  1. Parse the form payload (signature already verified by the dependency).
  2. Strip the 'whatsapp:' prefix from the From address to get a clean
     phone number we match against the database.
  3. Get or create the Conversation row in Postgres (audit trail anchor).
  4. Log the inbound message.
  5. Decide which handler runs:
     - Pending registration in 'pending' status → registration handler
     - Recognised Customer → customer handler
     - Unknown phone → registration handler (will create the row)
  6. Send the reply via TwiML (synchronous; Twilio delivers it).
  7. Log the outbound reply.

LLM safety valve (Task 6) sits in step 6 — if the customer handler
returns None (no fast-path match), we hand off to Celery and reply with
a placeholder for now. The Celery worker will send the real reply via
the REST API once it has the LLM response.
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
)
from app.services import (
    pending_registration_service as pr_svc,
)

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
    pending = pr_svc.get_pending_by_phone(db, phone)

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
    reply = _dispatch(db, phone, body, customer, pending)

    if reply is None:
        # LLM safety valve takes over. Enqueue the Celery worker —
        # it'll parse, match, write a cart, and send the outbound
        # asynchronously via Twilio's REST API.
        #
        # We commit FIRST so the inbound message + conversation row
        # are visible to the worker (which uses its own session). The
        # outbound from the worker logs itself.
        db.commit()

        from app.tasks.llm import parse_and_send

        # Customer is guaranteed non-None when reply is None — only
        # Case 3 (registered customer) reaches the LLM branch.
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

    # === Log the outbound ===
    conversation_log.log_outbound_message(
        db,
        conversation_id=conversation.id,
        body=reply,
        twilio_sid=None,
    )
    db.commit()

    return _twiml_response(reply)


def _empty_twiml_response() -> Response:
    """TwiML response with no message body.

    Used when the LLM safety valve will deliver the reply asynchronously
    via Twilio's REST API — we still have to give Twilio a valid TwiML
    response to the webhook, just one that doesn't include a <Message>
    tag. Twilio accepts this and sends nothing immediately.
    """
    twiml = '<?xml version="1.0" encoding="UTF-8"?>\n<Response></Response>'
    return Response(content=twiml, media_type="application/xml")


def _dispatch(
    db: Session,
    phone: str,
    body: str,
    customer,
    pending,
) -> str | None:
    """Pick the right handler and return its reply text.

    Decision order:
      1. Customer + still has a 'pending' registration row (unusual,
         shouldn't happen at runtime) → fall through to customer_handler.
         The pending row is residual; the customer is approved.
      2. Pending registration in 'pending' status → registration_handler.
         Includes 'rejected' status which the handler also covers.
      3. Customer recognised by phone → customer_handler, with LLM
         placeholder fallback if the handler returns None.
      4. Truly unknown phone → registration_handler (creates the row).
    """
    # Case 1: pending in pending status → registration flow drives this
    if pending and pending.status == "pending":
        return registration_handler.handle_registration_message(db, phone, body)

    # Case 2: rejected pending registration → registration_handler will
    # return the rejected message
    if pending and pending.status == "rejected":
        return registration_handler.handle_registration_message(db, phone, body)

    # Case 3: known customer → fast-path or LLM
    # Case 3: known customer → fast-path or LLM
    if customer:
        reply = customer_handler.handle_customer_message(db, customer, body)
        if reply is None:
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
        return reply

    # Case 4: truly unknown phone → start registration
    return registration_handler.handle_registration_message(db, phone, body)


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
