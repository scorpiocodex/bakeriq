"""LLM-related background tasks.

Two tasks live here:

  parse_free_text(text)
    Just the parse step. Returns the structured items dict. Used by
    unit tests and the original Substep 3 smoke test.

  parse_and_send(customer_id, conversation_id, phone, body)
    The full pipeline used by the webhook. Parses, matches, writes
    the pre-populated cart, issues a token, sends the WhatsApp reply
    (two messages: parse confirmation + cart-link Content Template),
    logs to conversation_messages. This is the "fire-and-forget"
    target enqueued by webhooks.py when handle_customer_message
    returns None.

Why two tasks not one:
  - parse_free_text is a pure function with no side effects, easy to
    test in isolation.
  - parse_and_send has multiple side effects (Redis write, DB writes,
    Twilio calls) and is tested by mocking those at the call boundary.
  - Splitting keeps the parser reusable if we want to call it from
    somewhere else later (e.g. an admin "preview LLM parse" tool).

Retry policy:
  - ollama.ResponseError triggers autoretry — transient connection
    or model-load hiccups recover after a few seconds.
  - Other exceptions (DB errors, Twilio failures, etc.) don't
    autoretry. They surface as task failures in the logs. We accept
    losing one customer's LLM-parse rather than risk duplicate
    WhatsApp sends from a retry of a partially-completed task.

Outbound shape (Substep 5):
  - Matched: [Reply.text(parse confirmation), cart_link_reply(token, link)]
  - Dropped-only (nothing matched): [Reply.text(MSG_NOTHING_AVAILABLE), fallback_reply()]
  - No parse: [Reply.text(MSG_NO_MATCH), nav_reply()]
  The two-message pattern mirrors customer_handler — prose answer
  followed by a tappable-button template. fallback_reply is used in
  the dropped-only branch because its Menu button is the natural
  next action ("see what IS available"); the other branches use
  nav_reply (Reorder / New / Status).
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
from app.services.reply import Reply
from app.services.template_replies import cart_link_reply, fallback_reply, nav_reply

logger = logging.getLogger(__name__)


# Fallback prose — kept short since the accompanying template surfaces
# the nav options as tappable buttons rather than text prompts.
MSG_NO_MATCH = "Sorry, I didn't catch that."

MSG_NOTHING_AVAILABLE = "Sorry, I couldn't find any of those items on today's menu."


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
      3. Decide outcome and build the Reply sequence:
         - matched: parse-confirmation prose + cart-link template
         - dropped only: "nothing available" prose + fallback template
                         (Menu / New / Status buttons)
         - no parse: "didn't catch that" prose + nav template
                     (Reorder / New / Status buttons)
      4. Send all replies via Twilio's REST API. send_replies logs
         each outbound to conversation_messages itself.
      5. Commit. Any earlier db.flush() writes (the token row, e.g.)
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

        # 3. Build replies based on outcome
        replies: list[Reply]
        if matched:
            handoff = handoff_to_web(
                db,
                customer=customer,
                matched=matched,
                dropped_names=dropped,
            )
            replies = [
                Reply.text(handoff.summary_body),
                cart_link_reply(handoff.token, handoff.link),
            ]
            outcome = "handoff"
        elif dropped:
            # LLM understood "they want food" but nothing was in the
            # catalog. fallback_reply has the Menu button — the
            # natural next action ("see what IS available").
            replies = [Reply.text(MSG_NOTHING_AVAILABLE), fallback_reply()]
            outcome = "nothing_available"
        else:
            # Parser returned nothing — no order intent detected.
            replies = [Reply.text(MSG_NO_MATCH), nav_reply()]
            outcome = "no_match"

        # 4. Send via Twilio. send_replies logs each outbound to
        # conversation_messages itself, so no separate log call here.
        whatsapp_sender.send_replies(
            db,
            conversation_id=conversation_uuid,
            to_phone=phone,
            replies=replies,
        )

        # 5. Commit token + cart + outbound logs in one transaction.
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
