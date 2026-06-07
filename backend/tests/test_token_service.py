"""Tests for the web session token service — auth for customer web app links."""

from datetime import datetime, timedelta, timezone

import pytest
from app.models.customer import Customer
from app.models.web_session_token import WebSessionToken
from app.services.token_service import (
    TOKEN_TTL_MINUTES,
    consume_token,
    issue_token,
    validate_token,
)


@pytest.fixture
def customer(db_session):
    """A persisted customer to attach tokens to."""
    c = Customer(
        name="Token Tester",
        primary_phone="+919888777111",
        whatsapp_enabled=True,
        is_active=True,
    )
    db_session.add(c)
    db_session.commit()
    db_session.refresh(c)
    return c


def test_issue_token_creates_row_with_expected_fields(db_session, customer):
    """A freshly issued token is persisted with the right shape."""
    row = issue_token(db_session, customer=customer, kind="reorder")
    db_session.commit()

    assert row is not None
    # 32 chars from secrets.token_urlsafe(24) — 24 bytes → 32 base64url chars
    assert len(row.token) == 32
    assert row.customer_id == customer.id
    assert row.kind == "reorder"
    assert row.consumed_at is None
    # Expiry is within a second of (now + TOKEN_TTL_MINUTES)
    expected = datetime.now(timezone.utc) + timedelta(minutes=TOKEN_TTL_MINUTES)
    delta = abs((row.expires_at - expected).total_seconds())
    assert delta < 2  # 2-second tolerance for execution time


def test_issue_token_rejects_invalid_kind(db_session, customer):
    """Only 'reorder', 'new', 'edit' are accepted kinds."""
    with pytest.raises(ValueError, match="Invalid token kind"):
        issue_token(db_session, customer=customer, kind="bogus")


def test_issue_token_accepts_all_three_kinds(db_session, customer):
    """All three valid kinds round-trip correctly."""
    for kind in ("reorder", "new", "edit"):
        row = issue_token(db_session, customer=customer, kind=kind)
        assert row.kind == kind
    db_session.commit()


def test_validate_token_returns_row_for_fresh_token(db_session, customer):
    """The happy path — issue then validate."""
    row = issue_token(db_session, customer=customer, kind="reorder")
    db_session.commit()

    validated = validate_token(db_session, row.token)
    assert validated is not None
    assert validated.token == row.token
    assert validated.customer_id == customer.id


def test_validate_token_returns_none_for_unknown_token(db_session):
    """A token that was never issued returns None."""
    result = validate_token(db_session, "this-token-does-not-exist")
    assert result is None


def test_validate_token_returns_none_for_expired_token(db_session, customer):
    """A token past its expires_at is rejected — no grace period."""
    row = issue_token(db_session, customer=customer, kind="reorder")
    # Backdate expiry by 1 second so it's just-expired
    row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db_session.commit()

    result = validate_token(db_session, row.token)
    assert result is None


def test_validate_token_returns_none_for_consumed_token(db_session, customer):
    """Once consumed, the token can't be used again — even within TTL."""
    row = issue_token(db_session, customer=customer, kind="reorder")
    db_session.commit()
    consume_token(db_session, row)
    db_session.commit()

    result = validate_token(db_session, row.token)
    assert result is None


def test_consume_token_sets_consumed_at(db_session, customer):
    """consume_token marks the row; subsequent validate calls reject it."""
    row = issue_token(db_session, customer=customer, kind="reorder")
    db_session.commit()
    assert row.consumed_at is None

    consume_token(db_session, row)
    db_session.commit()

    refreshed = db_session.get(WebSessionToken, row.token)
    assert refreshed is not None
    assert refreshed.consumed_at is not None
    # consumed_at should be roughly now
    delta = abs((refreshed.consumed_at - datetime.now(timezone.utc)).total_seconds())
    assert delta < 2
