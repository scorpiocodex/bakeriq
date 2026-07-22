"""Web session token service — auth for customer web app links.

When the bot sends a "tap to reorder" WhatsApp link, the path includes
a token from this table. The customer web app uses the token to:

  1. Authenticate ("yes, this customer can edit this cart")
  2. Identify what kind of session (reorder | new | edit)
  3. Know which customer the cart belongs to

Token lifecycle:
  - issue_token() — creates the row, returns the token string
  - validate_token() — checks not expired, not consumed; returns the row
  - consume_token() — marks consumed_at when 'Place order' is hit; the
    token can't be used to edit further after this

Tokens are session-style (multi-use during their 30-min TTL) until
consumed. A customer can open the link, save the cart, come back via
the same link, edit again, then finally place the order — all on one
token. Once placed, the token is dead.
"""

import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.customer import Customer
from app.models.web_session_token import WebSessionToken

TOKEN_TTL_MINUTES = 30
VALID_KINDS = {"reorder", "new", "edit"}


def issue_token(
    db: Session,
    *,
    customer: Customer,
    kind: str,
) -> WebSessionToken:
    """Generate a new web session token for a customer.

    The token string is 32 characters — secrets.token_urlsafe(24) yields
    32 chars of URL-safe random data (192 bits of entropy, more than
    enough). It's URL-safe so it embeds cleanly in the WhatsApp link
    path without encoding.

    A customer can have multiple active tokens at once (e.g. they tapped
    "Reorder last" twice, accidentally). We don't deduplicate — each tap
    issues a fresh token. The previous one expires naturally at 30 min.
    """
    if kind not in VALID_KINDS:
        raise ValueError(f"Invalid token kind {kind!r}; valid: {sorted(VALID_KINDS)}")

    token = secrets.token_urlsafe(24)  # → 32-char string
    expires = datetime.now(timezone.utc) + timedelta(minutes=TOKEN_TTL_MINUTES)

    row = WebSessionToken(
        token=token,
        customer_id=customer.id,
        kind=kind,
        expires_at=expires,
    )
    db.add(row)
    db.flush()
    return row


def validate_token(db: Session, token: str) -> WebSessionToken | None:
    """Return the token row if it's valid (exists, not expired, not
    consumed); None otherwise.

    Validation is strict — no grace period after expiry. The customer
    can refresh by tapping the WhatsApp button again, which issues a
    fresh token.

    Reading via this function does NOT extend the token's expiry. We
    want a hard 30-minute window so abandoned carts naturally clear.
    """
    row = db.scalar(select(WebSessionToken).where(WebSessionToken.token == token))
    if row is None:
        return None

    now = datetime.now(timezone.utc)
    if row.expires_at < now:
        return None

    if row.consumed_at is not None:
        return None

    return row


def consume_token(db: Session, row: WebSessionToken) -> None:
    """Mark the token as consumed — locks it from further use.

    Called when the customer places the order. The web app can still
    show the order confirmation page, but the cart endpoints will
    reject this token from now on.
    """
    row.consumed_at = datetime.now(timezone.utc)
    db.flush()
