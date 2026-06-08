"""LLM-related background tasks.

Two tasks live here:

  parse_free_text(text)
    Just the parse step. Returns the structured items dict. Used by
    unit tests and the original Substep 3 smoke test.

  parse_and_send(customer_id, conversation_id, phone, body)
    The full pipeline used by the webhook. Parses, matches, writes
    the pre-populated cart, issues a token, sends the WhatsApp reply,
    logs it to conversation_messages. This is the "fire-and-forget"
    target enqueued by webhooks.py when handle_customer_message
    returns None.

Why two tasks not one:
  - parse_free_text is a pure function with no side effects, easy to
    test in isolation.
  - parse_and_send has multiple side effects (Redis write, DB writes,
    Twilio call) and is tested by mocking those at the call boundary.
  - Splitting keeps the parser reusable if we want to call it from
    somewhere else later (e.g. an admin "preview LLM parse" tool).

Retry policy:
  - ollama.ResponseError triggers autoretry — transient connection
    or model-load hiccups recover after a few seconds.
  - Other exceptions (DB errors, Twilio failures, etc.) don't
    autoretry. They surface as task failures in the logs. We accept
    losing one customer's LLM-parse rather than risk duplicate
    WhatsApp sends from a retry of a partially-completed task.
"""

from __future__ import annotations

import logging
from uuid import UUID

from ollama import ResponseError
from sqlalchemy import select

from app.core.celery_app import celery_app
from app.core.database import SessionLocal
from app.models.customer import Customer
from app.services import whatsapp_sender
from app.services.llm_cart_handoff_service import handoff_to_web
from app.services.llm_parser_service import parse_message
from app.services.product_matcher_service import match_items

logger = logging.getLogger(__name__)


# Fallback messages — the bot's voice when the LLM can't help.
MSG_NO_MATCH = (
    "Sorry, I didn't catch that. Try one of these:\n"
    "• Reply *menu* to see today's items\n"
    "• Reply *new order* to start an order\n"
    "• Reply *status* to check your latest order"
)

MSG_NOTHING_AVAILABLE = (
    "Sorry, I couldn't find any of those items on today's menu.\n"
    "\n"
    "Reply *menu* to see what's available."
)


@celery_app.task(
    name="bakeriq.llm.parse_free_text",
    autoretry_for=(ResponseError,),
    retry_backoff=10,
    retry_jitter=True,
)
def parse_free_text(text: str) -> dict:
    """Parse-only task — returns the LLM's structured interpretation.

    Used by tests and tooling, NOT by the webhook. Webhook uses
    parse_and_send below which includes the full pipeline.
    """
    logger.info(f"parse_free_text: text={text!r}")
    db = SessionLocal()
    try:
        result = parse_message(db, text)
        logger.info(f"parse_free_text: parsed {len(result['items'])} item(s)")
        return result
    finally:
        db.close()


@celery_app.task(
    name="bakeriq.llm.parse_and_send",
    autoretry_for=(ResponseError,),
    retry_backoff=10,
    retry_jitter=True,
)
def parse_and_send(
    customer_id: str,
    conversation_id: str,
    phone: str,
    body: str,
) -> dict:
    """Full LLM safety-valve pipeline. Enqueued by the webhook when
    fast-path keyword matching returns None.

    Steps:
      1. Parse the message via Ollama.
      2. Match LLM-extracted names to real products.
      3. If anything matched: write a pre-populated cart, issue a
         'new'-kind token, build the cart-summary message.
      4. If nothing matched (parser empty OR all items dropped): send
         the generic fallback so the customer isn't left in silence.
      5. Send the chosen message via Twilio. The send itself logs the
         outbound to conversation_messages.
      6. Commit. Any earlier db.flush() writes (the token row, e.g.)
         only persist if we reach this point.

    Args take str instead of UUID because Celery's JSON serialiser
    doesn't handle UUID natively — we serialise at the boundary and
    parse on receipt.

    Returns: A small dict summarising what happened, mostly for log
        visibility. Not consumed by the webhook (fire-and-forget).
    """
    logger.info(f"parse_and_send: customer_id={customer_id} body={body!r}")

    customer_uuid = UUID(customer_id)
    conversation_uuid = UUID(conversation_id)

    db = SessionLocal()
    try:
        # Re-load the customer in this session — we got an ID over the
        # wire, not the ORM object. Cheaper than a full load + safer
        # than passing relationship-loaded state across processes.
        customer = db.scalar(select(Customer).where(Customer.id == customer_uuid))
        if customer is None:
            # Race condition: customer was deleted between webhook and
            # worker pickup. Extremely unlikely; log loudly and bail.
            logger.error(f"parse_and_send: customer {customer_id} not found")
            return {"status": "customer_not_found"}

        # 1. Parse
        parsed = parse_message(db, body)
        logger.info(f"parse_and_send: LLM returned {len(parsed['items'])} item(s)")

        # 2. Match
        matched, dropped = match_items(db, parsed["items"])
        logger.info(f"parse_and_send: matched={len(matched)} dropped={len(dropped)}")

        # 3 or 4. Decide which message to send
        if matched:
            handoff = handoff_to_web(
                db,
                customer=customer,
                matched=matched,
                dropped_names=dropped,
            )
            message_to_send = handoff.message_text
            outcome = "handoff"
        elif dropped:
            # LLM understood "they want food" but nothing was in the
            # catalog. More specific message than the generic fallback.
            message_to_send = MSG_NOTHING_AVAILABLE
            outcome = "nothing_available"
        else:
            # Parser returned nothing — no order intent detected.
            message_to_send = MSG_NO_MATCH
            outcome = "no_match"

        # 5. Send via Twilio. send_text logs to conversation_messages
        # itself, so we don't need a separate log call here.
        whatsapp_sender.send_text(
            db,
            conversation_id=conversation_uuid,
            to_phone=phone,
            body=message_to_send,
        )

        # 6. Commit token + cart + outbound log in one transaction.
        db.commit()

        logger.info(f"parse_and_send: outcome={outcome}")
        return {
            "status": "sent",
            "outcome": outcome,
            "matched": len(matched),
            "dropped": len(dropped),
        }

    except Exception:
        # We don't want partial state — a token issued but no message
        # sent, or vice versa. Roll back; the autoretry on
        # ollama.ResponseError will run the whole thing again.
        db.rollback()
        raise
    finally:
        db.close()
