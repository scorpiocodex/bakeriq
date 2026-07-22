"""Registration handler — issues a webform link when an unknown phone
messages the bot.

Post-Phase 3.5 refactor: this file previously contained a ~200-line
conversational state machine that asked the customer for name and area
over multiple WhatsApp turns. The new architecture replaces that with
a single Content Template card containing a "Register now" CTA button
that opens a webform on the customer's phone.

Everything the customer used to type into WhatsApp gets typed into
the form instead — one URL round-trip, structured fields, validation,
matches how the cart-link flow works.

Contract:
  handle_registration_message(db, phone, body) -> list[Reply]

Returns a Reply list ready for the webhook to send. Always returns
the registration CTA card unless the phone is already registered as
a Customer (in which case the caller shouldn't have routed here at
all — we return an empty list as a defensive no-op).

The `body` argument is unused. It's kept in the signature because the
webhook dispatcher passes it uniformly to all handlers; if we later
add smart handling (e.g. re-issue a fresh link if the customer
typed 'help' after their old link expired), body is where we'd read
that from.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.services import registration_token_service
from app.services.reply import Reply
from app.services.template_replies import registration_link_reply


def handle_registration_message(
    db: Session,
    phone: str,
    body: str,  # noqa: ARG001 — reserved for future smart handling
) -> list[Reply]:
    """Issue a fresh registration webform link.

    Idempotency:
      - If the phone already has an unconsumed unexpired token, we
        reuse it (same URL) so a customer who taps the link twice
        gets the same session.
      - If the previous token expired, we issue a fresh one.
      - If the previous token was consumed (they already submitted
        the form), we still issue a fresh one — but the form will
        show an "already registered" state since the token service
        checks phone-level state.

    The webform URL that ends up in the WhatsApp card body:
        https://<PUBLIC_BASE_URL>/web/register/<TOKEN>
    """
    token, link = registration_token_service.get_or_issue_token(db, phone=phone)
    return [registration_link_reply(token, link)]
