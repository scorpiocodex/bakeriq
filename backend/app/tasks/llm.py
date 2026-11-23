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

Retry policy (post-hardening):
  Five exception classes trigger autoretry with exponential backoff
  (~5s, 10s, 20s, capped at 30s, jittered). See `RETRY_EXCEPTIONS`
  below for the full list and rationale per class.

  The retry tuple deliberately does NOT include broad Exception
  catch-all — DB errors, Twilio rate limits, programmer errors etc.
  should surface as task failures rather than auto-retrying. Auto-
  retrying those risks duplicate sends or amplifying downstream
  problems.

  When retries exhaust the task hits the MaxRetriesExceededError
  branch in parse_and_send and sends MSG_SERVICE_DEGRADED so the
  customer is never left in silence.

Outbound shape (Substep 5):
  - Matched: [Reply.text(parse confirmation), cart_link_reply(token, link)]
  - Dropped-only (nothing matched): [Reply.text(MSG_NOTHING_AVAILABLE), fallback_reply()]
  - No parse: [Reply.text(MSG_NO_MATCH), nav_reply()]
  - Retries exhausted: [Reply.text(MSG_SERVICE_DEGRADED), nav_reply()]

  The two-message pattern mirrors customer_handler — prose answer
  followed by a tappable-button template. fallback_reply is used in
  the dropped-only branch because its Menu button is the natural
  next action ("see what IS available"); the other branches use
  nav_reply (Reorder / New / Status).

Result-dict status values (post-hardening):
  - "sent" — all replies sent successfully
  - "partial_send_failure" — some replies sent, some failed at Twilio
  - "all_sends_failed" — all replies failed at Twilio
  - "fallback_after_retry_exhausted" — pipeline retries exhausted,
    fired MSG_SERVICE_DEGRADED fallback message
  - "fallback_send_failed" — even the fallback message couldn't reach
    Twilio. Customer is in silence; only an alert can help here.
  - "customer_not_found" — customer was deleted between webhook and
    worker pickup; task no-ops gracefully.
"""

from __future__ import annotations

import logging
from uuid import UUID

# Deliberately `httpx`, not `httpx2`. The exceptions in RETRY_EXCEPTIONS are the ones the
# Ollama SDK raises, and the SDK uses httpx internally (ollama 0.4.4 requires httpx<0.28).
# An httpx2 exception class would never match them. tests/tasks/test_llm_retry_exceptions.py
# provokes a real refused connection to prove the tuple still catches what the SDK raises.
import httpx
from celery.exceptions import MaxRetriesExceededError
from ollama import RequestError, ResponseError
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


# Retry-triggering exceptions, with one-line rationales.
#
#   ResponseError              ollama SDK — model returned an error response
#                              (often transient, e.g. model still loading
#                              after the daemon restarted).
#   RequestError               ollama SDK — connection/request setup error
#                              before the model was even called.
#   httpx.ConnectError         Network unreachable; Ollama daemon down;
#                              firewall blocking the bridge. We observed
#                              this firsthand during the docker0/UFW
#                              incident; the old narrow tuple missed it.
#   httpx.ConnectTimeout       Routing layer accepted the connection but
#                              the server never completed the handshake
#                              within the timeout. Same root causes as
#                              above, usually transient.
#   httpx.ReadTimeout          Connection established, request sent, but
#                              the server didn't finish responding in
#                              time. Cold-loading the llama3.2:3b weights
#                              after a daemon restart routinely takes
#                              30-60s on the dev box; the first request
#                              after a restart hits this.
RETRY_EXCEPTIONS: tuple[type[Exception], ...] = (
    ResponseError,
    RequestError,
    httpx.ConnectError,
    httpx.ConnectTimeout,
    httpx.ReadTimeout,
)


# Fallback prose — kept short since the accompanying template surfaces
# the nav options as tappable buttons rather than text prompts.
MSG_NO_MATCH = "Sorry, I didn't catch that."

MSG_NOTHING_AVAILABLE = "Sorry, I couldn't find any of those items on today's menu."

# Used by the retry-exhausted fallback path. Distinct from MSG_NO_MATCH
# because the user's input wasn't gibberish — the system was unable to
# process it. Says so plainly and gives them an action that's likely to
# work shortly.
MSG_SERVICE_DEGRADED = (
    "We're having trouble processing your message. "
    "Please try again in a moment, or tap an option below."
)


@celery_app.task(
    name="bakeriq.llm.parse_free_text",
    autoretry_for=RETRY_EXCEPTIONS,
    retry_backoff=5,
    retry_backoff_max=30,
    retry_jitter=True,
    max_retries=3,
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
    bind=True,
    name="bakeriq.llm.parse_and_send",
    autoretry_for=RETRY_EXCEPTIONS,
    retry_backoff=5,
    retry_backoff_max=30,
    retry_jitter=True,
    max_retries=3,
)
def parse_and_send(
    self,  # bound task — needed to surface retry state in MaxRetriesExceededError handling
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
      4. Send all replies via Twilio's REST API. send_replies returns
         a list of SIDs (or None for individual failures); we check
         that list to report honest result status rather than always
         claiming "sent".
      5. Commit. Any earlier db.flush() writes (the token row, e.g.)
         only persist if we reach this point.

    Retry/fallback behavior:
      - Transient network errors (Ollama down, slow cold-load) trigger
        autoretry per RETRY_EXCEPTIONS, with ~5/10/20s backoff.
      - When retries exhaust, MaxRetriesExceededError is caught and we
        fire MSG_SERVICE_DEGRADED so the customer is informed rather
        than left in silence.

    Args take str instead of UUID because Celery's JSON serialiser
    doesn't handle UUID natively — we serialise at the boundary and
    parse on receipt.

    Returns:
        Status dict describing what actually happened. See module
        docstring for the full set of status values.
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

        # 1. Parse. This is the step that raises RETRY_EXCEPTIONS when
        # Ollama is unreachable; Celery's autoretry catches them above
        # this stack frame.
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

        # 4. Send via Twilio. send_replies returns list[str | None]; we
        # inspect it to report honestly. Previously this always logged
        # outcome=X status=sent even when both Twilio calls failed
        # (observed during the June 9 quota-exhaustion incident).
        sids = whatsapp_sender.send_replies(
            db,
            conversation_id=conversation_uuid,
            to_phone=phone,
            replies=replies,
        )

        # 5. Commit. We always commit regardless of Twilio success —
        # the token + cart + log rows belong in the DB so the audit
        # trail shows we tried. The status returned to Celery reflects
        # what actually reached the customer.
        db.commit()

        send_status = _classify_send_results(sids)
        logger.info(
            "parse_and_send: outcome=%s send_status=%s sids=%s",
            outcome,
            send_status,
            sids,
        )
        return {
            "status": send_status,
            "outcome": outcome,
            "matched": len(matched),
            "dropped": len(dropped),
            "sids": sids,
        }

    except MaxRetriesExceededError:
        # Retries against Ollama failed all the way through. The
        # customer is waiting for a reply we can't generate. Fall
        # back to MSG_SERVICE_DEGRADED so they're informed rather
        # than left in silence.
        #
        # NOTE: we deliberately open a fresh DB session for this. The
        # outer session is in an unknown state after the chain of
        # retried failures; using it risks compounding errors.
        logger.error(
            "parse_and_send: retries exhausted for customer %s, "
            "firing MSG_SERVICE_DEGRADED",
            customer_id,
        )
        db.rollback()  # release any locks held by the outer session
        return _send_service_degraded_fallback(
            conversation_uuid=conversation_uuid,
            phone=phone,
        )

    except Exception:
        # Non-retried exception (programmer error, DB error, etc.).
        # Roll back so we don't leave half-written state behind, then
        # re-raise so Celery surfaces it as a task failure for ops to
        # investigate. The customer is left without a reply — this is
        # the cost of refusing to auto-retry classes of error we
        # can't reason about safely.
        db.rollback()
        raise

    finally:
        db.close()


def _classify_send_results(sids: list[str | None]) -> str:
    """Translate the send_replies result list into a status string.

    sids semantics:
      - Every entry is a Twilio Message SID on success, None on failure.
      - We log every attempt regardless of success at the
        conversation_messages level (whatsapp_sender does that itself).
      - The status we return here is about delivery, not logging.
    """
    if not sids:
        # Defensive: shouldn't happen with current callers, but if a
        # future branch ever produces an empty replies list this
        # surfaces it rather than claiming success silently.
        return "all_sends_failed"
    if all(sid is None for sid in sids):
        return "all_sends_failed"
    if any(sid is None for sid in sids):
        return "partial_send_failure"
    return "sent"


def _send_service_degraded_fallback(
    *,
    conversation_uuid: UUID,
    phone: str,
) -> dict:
    """Send MSG_SERVICE_DEGRADED + nav buttons after retry exhaustion.

    Wrapped in its own try/except so a Twilio failure here doesn't
    cascade into another exception bubbling up to Celery (which would
    just retry the whole pipeline again and re-exhaust). If even the
    fallback can't send, we log loudly and return a status the
    monitoring side can pick up on.
    """
    fallback_db = SessionLocal()
    try:
        replies = [
            Reply.text(MSG_SERVICE_DEGRADED),
            nav_reply(),
        ]
        sids = whatsapp_sender.send_replies(
            fallback_db,
            conversation_id=conversation_uuid,
            to_phone=phone,
            replies=replies,
        )
        fallback_db.commit()

        send_status = _classify_send_results(sids)
        if send_status == "sent":
            logger.info(
                "parse_and_send: MSG_SERVICE_DEGRADED delivered to %s",
                phone,
            )
            return {
                "status": "fallback_after_retry_exhausted",
                "outcome": "service_degraded",
                "sids": sids,
            }

        # Twilio is also having a bad day. There is genuinely nothing
        # left we can do for this customer in this task. Log loudly so
        # ops sees it; the alerting layer can pick up on this status.
        logger.error(
            "parse_and_send: MSG_SERVICE_DEGRADED ALSO failed for %s; "
            "customer is in silence. send_status=%s sids=%s",
            phone,
            send_status,
            sids,
        )
        return {
            "status": "fallback_send_failed",
            "outcome": "service_degraded",
            "sids": sids,
        }

    except Exception:
        # Fallback path itself crashed (DB issue, malformed config,
        # etc.). Log and return; do NOT re-raise — Celery would retry
        # the whole pipeline which has already exhausted retries.
        logger.exception(
            "parse_and_send: MSG_SERVICE_DEGRADED handler crashed for %s",
            phone,
        )
        fallback_db.rollback()
        return {
            "status": "fallback_send_failed",
            "outcome": "service_degraded",
        }

    finally:
        fallback_db.close()
