"""Tests for app.services.registration_token_service.

Covers the token lifecycle: issue, look up (valid + details), consume,
and the idempotent get_or_issue behavior.

Pure DB tests — no Twilio, no external services. `db_session` fixture
from conftest provides an isolated test transaction.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.models.registration_token import RegistrationToken
from app.services import registration_token_service as rt_svc
from sqlalchemy import select

PHONE_A = "+919888777001"
PHONE_B = "+919888777002"


# ============================================================
# issue_token
# ============================================================


class TestIssueToken:
    def test_creates_row_with_correct_phone(self, db_session):
        token, url = rt_svc.issue_token(db_session, phone=PHONE_A)
        db_session.commit()

        row = db_session.scalar(
            select(RegistrationToken).where(RegistrationToken.phone == PHONE_A)
        )
        assert row is not None
        assert row.phone == PHONE_A
        assert row.token == token

    def test_returns_url_with_public_base(self, db_session):
        """URL should be settings.PUBLIC_BASE_URL + /web/register/<token>."""
        from app.core.config import settings

        token, url = rt_svc.issue_token(db_session, phone=PHONE_A)
        db_session.commit()

        assert url.startswith(settings.PUBLIC_BASE_URL.rstrip("/"))
        assert url.endswith(f"/web/register/{token}")

    def test_token_is_url_safe(self, db_session):
        """secrets.token_urlsafe output contains only URL-safe chars."""
        token, _ = rt_svc.issue_token(db_session, phone=PHONE_A)
        db_session.commit()
        # URL-safe base64: A-Z a-z 0-9 - _
        assert all(c.isalnum() or c in ("-", "_") for c in token), (
            f"Non-URL-safe char in token: {token!r}"
        )

    def test_expires_12_hours_from_now(self, db_session):
        _, _ = rt_svc.issue_token(db_session, phone=PHONE_A)
        db_session.commit()

        row = db_session.scalar(
            select(RegistrationToken).where(RegistrationToken.phone == PHONE_A)
        )
        now = datetime.now(timezone.utc)
        assert row.expires_at > now + timedelta(hours=11, minutes=59)
        assert row.expires_at < now + timedelta(hours=12, minutes=1)


# ============================================================
# get_or_issue_token — idempotent reuse
# ============================================================


class TestGetOrIssueToken:
    def test_first_call_creates_new(self, db_session):
        token, _ = rt_svc.get_or_issue_token(db_session, phone=PHONE_A)
        db_session.commit()

        rows = db_session.scalars(
            select(RegistrationToken).where(RegistrationToken.phone == PHONE_A)
        ).all()
        assert len(rows) == 1
        assert rows[0].token == token

    def test_second_call_returns_same_token(self, db_session):
        """Two calls within the validity window should return the same URL."""
        token1, url1 = rt_svc.get_or_issue_token(db_session, phone=PHONE_A)
        db_session.commit()
        token2, url2 = rt_svc.get_or_issue_token(db_session, phone=PHONE_A)
        db_session.commit()

        assert token1 == token2
        assert url1 == url2
        # And only one row was created
        rows = db_session.scalars(
            select(RegistrationToken).where(RegistrationToken.phone == PHONE_A)
        ).all()
        assert len(rows) == 1

    def test_reissues_after_consumption(self, db_session):
        """Once the previous token is consumed, a new one should be issued."""
        token1, _ = rt_svc.get_or_issue_token(db_session, phone=PHONE_A)
        row1 = rt_svc.get_valid_token(db_session, token1)
        assert row1 is not None
        rt_svc.consume_token(db_session, row1)
        db_session.commit()

        token2, _ = rt_svc.get_or_issue_token(db_session, phone=PHONE_A)
        db_session.commit()

        assert token1 != token2

    def test_reissues_after_expiry(self, db_session):
        """If the previous token expired, a new one should be issued."""
        # Issue a token, then manually expire it
        token1, _ = rt_svc.get_or_issue_token(db_session, phone=PHONE_A)
        row1 = db_session.scalar(
            select(RegistrationToken).where(RegistrationToken.token == token1)
        )
        row1.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        db_session.commit()

        token2, _ = rt_svc.get_or_issue_token(db_session, phone=PHONE_A)
        db_session.commit()

        assert token1 != token2

    def test_different_phones_get_different_tokens(self, db_session):
        token_a, _ = rt_svc.get_or_issue_token(db_session, phone=PHONE_A)
        token_b, _ = rt_svc.get_or_issue_token(db_session, phone=PHONE_B)
        db_session.commit()

        assert token_a != token_b


# ============================================================
# get_valid_token
# ============================================================


class TestGetValidToken:
    def test_returns_row_for_active_token(self, db_session):
        token, _ = rt_svc.issue_token(db_session, phone=PHONE_A)
        db_session.commit()

        row = rt_svc.get_valid_token(db_session, token)
        assert row is not None
        assert row.token == token

    def test_returns_none_for_nonexistent(self, db_session):
        assert rt_svc.get_valid_token(db_session, "does-not-exist") is None

    def test_returns_none_for_consumed(self, db_session):
        token, _ = rt_svc.issue_token(db_session, phone=PHONE_A)
        row = rt_svc.get_valid_token(db_session, token)
        rt_svc.consume_token(db_session, row)
        db_session.commit()

        assert rt_svc.get_valid_token(db_session, token) is None

    def test_returns_none_for_expired(self, db_session):
        token, _ = rt_svc.issue_token(db_session, phone=PHONE_A)
        row = db_session.scalar(
            select(RegistrationToken).where(RegistrationToken.token == token)
        )
        row.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        db_session.commit()

        assert rt_svc.get_valid_token(db_session, token) is None


# ============================================================
# get_token_details — status distinction for finer error messages
# ============================================================


class TestGetTokenDetails:
    def test_ok_for_active(self, db_session):
        token, _ = rt_svc.issue_token(db_session, phone=PHONE_A)
        db_session.commit()

        row, status = rt_svc.get_token_details(db_session, token)
        assert status == "ok"
        assert row is not None

    def test_not_found_for_nonexistent(self, db_session):
        row, status = rt_svc.get_token_details(db_session, "does-not-exist")
        assert status == "not_found"
        assert row is None

    def test_consumed_status(self, db_session):
        token, _ = rt_svc.issue_token(db_session, phone=PHONE_A)
        row = rt_svc.get_valid_token(db_session, token)
        rt_svc.consume_token(db_session, row)
        db_session.commit()

        row2, status = rt_svc.get_token_details(db_session, token)
        assert status == "consumed"
        assert row2 is None

    def test_expired_status(self, db_session):
        token, _ = rt_svc.issue_token(db_session, phone=PHONE_A)
        row = db_session.scalar(
            select(RegistrationToken).where(RegistrationToken.token == token)
        )
        row.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        db_session.commit()

        row2, status = rt_svc.get_token_details(db_session, token)
        assert status == "expired"
        assert row2 is None


# ============================================================
# consume_token
# ============================================================


class TestConsumeToken:
    def test_sets_consumed_at(self, db_session):
        token, _ = rt_svc.issue_token(db_session, phone=PHONE_A)
        row = rt_svc.get_valid_token(db_session, token)
        assert row.consumed_at is None

        rt_svc.consume_token(db_session, row)
        db_session.commit()

        # Re-fetch and check
        fresh = db_session.scalar(
            select(RegistrationToken).where(RegistrationToken.token == token)
        )
        assert fresh.consumed_at is not None
