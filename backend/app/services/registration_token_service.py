"""RegistrationToken service — issue, look up, consume.

Mirror of web_link_service but phone-based and one-shot. Design
decisions documented in models/registration_token.py.

Public API:
    issue_token(db, phone) -> (token_str, url)
    get_or_issue_token(db, phone) -> (token_str, url)  # idempotent
    get_valid_token(db, token_str) -> RegistrationToken | None
    consume_token(db, token) -> None
"""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.registration_token import RegistrationToken

# 12-hour validity window. Long enough that a customer who got the
# link at night can register the next morning, short enough that
# stolen tokens don't grant long-lasting access.
TOKEN_TTL = timedelta(hours=12)

# URL-safe random token length. secrets.token_urlsafe(n) produces
# roughly ceil(n * 4/3) characters. 24 bytes → ~32 chars, which fits
# nicely in the 64-char column and is more than enough entropy.
TOKEN_BYTES = 24


def _build_url(token: str) -> str:
    base = settings.PUBLIC_BASE_URL.rstrip("/")
    return f"{base}/web/register/{token}"


def issue_token(db: Session, *, phone: str) -> tuple[str, str]:
    """Create a fresh registration token for `phone`.

    Returns (token_string, full_url). The URL is what the customer
    ultimately taps in WhatsApp.

    This ALWAYS creates a new row. To reuse an active token, call
    get_or_issue_token instead — that's what the handler uses.
    """
    token_str = secrets.token_urlsafe(TOKEN_BYTES)
    now = datetime.now(timezone.utc)
    row = RegistrationToken(
        phone=phone,
        token=token_str,
        created_at=now,
        expires_at=now + TOKEN_TTL,
    )
    db.add(row)
    db.flush()
    return token_str, _build_url(token_str)


def get_or_issue_token(db: Session, *, phone: str) -> tuple[str, str]:
    """Return the phone's active token if one exists, else issue a fresh one.

    'Active' means: not consumed, not expired.

    Idempotency for retries: a customer who taps 'send me the link
    again' should get the same URL if their previous link is still
    good. New token only when the old one is used or dead.
    """
    now = datetime.now(timezone.utc)
    existing = db.scalar(
        select(RegistrationToken).where(
            RegistrationToken.phone == phone,
            RegistrationToken.consumed_at.is_(None),
            RegistrationToken.expires_at > now,
        )
    )
    if existing:
        return existing.token, _build_url(existing.token)
    return issue_token(db, phone=phone)


def get_valid_token(db: Session, token_str: str) -> RegistrationToken | None:
    """Return the RegistrationToken row if `token_str` is valid, else None.

    Valid means: exists, not consumed, not expired. Anything else — 404,
    already used, past expiry — returns None. Callers translate that
    into the appropriate HTTP response (404 vs 410 vs 410).

    To distinguish "not found" from "already used" from "expired" for
    the frontend, use get_token_details instead.
    """
    now = datetime.now(timezone.utc)
    return db.scalar(
        select(RegistrationToken).where(
            RegistrationToken.token == token_str,
            RegistrationToken.consumed_at.is_(None),
            RegistrationToken.expires_at > now,
        )
    )


def get_token_details(
    db: Session, token_str: str
) -> tuple[RegistrationToken | None, str]:
    """Return (token_row, status_string) for finer-grained frontend responses.

    status_string is one of:
      'ok'           — token is valid, use the row
      'not_found'    — no such token
      'consumed'     — token was already used
      'expired'      — past expiry

    Row is None if status != 'ok'.
    """
    row = db.scalar(
        select(RegistrationToken).where(RegistrationToken.token == token_str)
    )
    if row is None:
        return None, "not_found"
    if row.consumed_at is not None:
        return None, "consumed"
    if row.expires_at <= datetime.now(timezone.utc):
        return None, "expired"
    return row, "ok"


def consume_token(db: Session, row: RegistrationToken) -> None:
    """Mark a token as consumed. Any further use returns 'consumed' status.

    Called by the form-submission endpoint after PendingRegistration
    is successfully created.
    """
    row.consumed_at = datetime.now(timezone.utc)
    db.flush()
