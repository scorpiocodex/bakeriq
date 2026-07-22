"""Tests for the /api/v1/register/{token} endpoints.

Covers both GET (token validation + phone pre-fill) and POST (form
submission → PendingRegistration creation + token consumption).

Uses the same TestClient pattern as test_cart_api.py — client + db_session
fixtures from conftest, no external mocks needed.

Note on payloads: address is REQUIRED on this endpoint. Approving a
registration copies the address straight into a Customer, where those
fields are mandatory — a name-only registration would create a Customer
that CustomerOut can't serialize, which takes down the whole customers
list. So every POST here sends a full payload via _payload(), and the
tests that check error paths override individual fields rather than
dropping them.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.models.customer import Customer
from app.models.pending_registration import PendingRegistration
from app.models.registration_token import RegistrationToken
from app.services import registration_token_service as rt_svc
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

PHONE = "+919888555001"


# ============================================================
# Helpers
# ============================================================


def _payload(**overrides) -> dict:
    """A valid registration submission, with optional field overrides.

    Keeps the error-path tests readable: they change the one field under
    test instead of restating the whole body.
    """
    body = {
        "name": "Test User",
        "address_line_1": "12 MG Road",
        "city": "Kochi",
        "state": "Kerala",
        "pincode": "682020",
    }
    body.update(overrides)
    return body


def _issue_token(db_session: Session, phone: str = PHONE) -> str:
    """Issue a token via the service, commit, return the token string."""
    token, _ = rt_svc.issue_token(db_session, phone=phone)
    db_session.commit()
    return token


def _expire_token(db_session: Session, token: str) -> None:
    """Backdate a token's expiry so it's already expired."""
    row = db_session.scalar(
        select(RegistrationToken).where(RegistrationToken.token == token)
    )
    assert row is not None
    row.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db_session.commit()


def _consume_token(db_session: Session, token: str) -> None:
    row = rt_svc.get_valid_token(db_session, token)
    assert row is not None
    rt_svc.consume_token(db_session, row)
    db_session.commit()


# ============================================================
# GET /api/v1/register/{token}
# ============================================================


class TestGetRegistrationToken:
    def test_returns_phone_for_valid_token(
        self, client: TestClient, db_session: Session
    ):
        token = _issue_token(db_session)

        response = client.get(f"/api/v1/register/{token}")
        assert response.status_code == 200
        data = response.json()
        assert data["phone"] == PHONE
        assert data["already_registered"] is False

    def test_flags_already_registered_customer(
        self, client: TestClient, db_session: Session
    ):
        """If a Customer exists for this phone, the response should say so."""
        customer = Customer(
            name="Existing User",
            primary_phone=PHONE,
            whatsapp_enabled=True,
            is_active=True,
            address_line_1="9 Old Road",
            city="Kochi",
            state="Kerala",
            pincode="682001",
        )
        db_session.add(customer)
        db_session.commit()

        token = _issue_token(db_session)

        response = client.get(f"/api/v1/register/{token}")
        assert response.status_code == 200
        data = response.json()
        assert data["phone"] == PHONE
        assert data["already_registered"] is True

    def test_404_for_nonexistent_token(self, client: TestClient):
        response = client.get("/api/v1/register/completely-fake-token")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_410_for_consumed_token(self, client: TestClient, db_session: Session):
        token = _issue_token(db_session)
        _consume_token(db_session, token)

        response = client.get(f"/api/v1/register/{token}")
        assert response.status_code == 410
        assert "already been used" in response.json()["detail"].lower()

    def test_410_for_expired_token(self, client: TestClient, db_session: Session):
        token = _issue_token(db_session)
        _expire_token(db_session, token)

        response = client.get(f"/api/v1/register/{token}")
        assert response.status_code == 410
        assert "expired" in response.json()["detail"].lower()


# ============================================================
# POST /api/v1/register/{token}
# ============================================================


class TestPostRegistration:
    """Form submission — creates PendingRegistration, consumes token."""

    def test_creates_pending_registration(
        self, client: TestClient, db_session: Session
    ):
        token = _issue_token(db_session)

        response = client.post(
            f"/api/v1/register/{token}",
            json=_payload(address_line_2="Near Junction"),
        )

        assert response.status_code == 200
        data = response.json()
        assert "registration_id" in data
        assert "message" in data

        # Verify the row landed with every field intact
        reg = db_session.scalar(
            select(PendingRegistration).where(PendingRegistration.phone == PHONE)
        )
        assert reg is not None
        assert reg.name == "Test User"
        assert reg.address_line_1 == "12 MG Road"
        assert reg.address_line_2 == "Near Junction"
        assert reg.city == "Kochi"
        assert reg.state == "Kerala"
        assert reg.pincode == "682020"
        assert reg.status == "awaiting_approval"

    def test_address_line_2_is_optional(self, client: TestClient, db_session: Session):
        """Line 2 is the one address field that may be omitted — it's
        optional on Customer too."""
        token = _issue_token(db_session)

        response = client.post(f"/api/v1/register/{token}", json=_payload())
        assert response.status_code == 200

        reg = db_session.scalar(
            select(PendingRegistration).where(PendingRegistration.phone == PHONE)
        )
        assert reg is not None
        assert reg.address_line_2 is None

    def test_consumes_token_on_success(self, client: TestClient, db_session: Session):
        token = _issue_token(db_session)

        response = client.post(f"/api/v1/register/{token}", json=_payload())
        assert response.status_code == 200

        # Token should now be consumed
        row = db_session.scalar(
            select(RegistrationToken).where(RegistrationToken.token == token)
        )
        assert row is not None
        assert row.consumed_at is not None

    def test_missing_name_returns_422(self, client: TestClient, db_session: Session):
        token = _issue_token(db_session)

        # Empty name — pydantic min_length=1 catches this
        response = client.post(f"/api/v1/register/{token}", json=_payload(name=""))
        assert response.status_code == 422

    def test_missing_address_returns_422(self, client: TestClient, db_session: Session):
        """Address is required. Without it, approving the registration
        would create a Customer with NULL address fields — which
        CustomerOut rejects, breaking the customers list for every row."""
        token = _issue_token(db_session)

        response = client.post(
            f"/api/v1/register/{token}",
            json={"name": "Minimal User"},
        )
        assert response.status_code == 422

        # And nothing was written
        reg = db_session.scalar(
            select(PendingRegistration).where(PendingRegistration.phone == PHONE)
        )
        assert reg is None

    def test_malformed_pincode_returns_422(
        self, client: TestClient, db_session: Session
    ):
        """Indian PIN codes are exactly 6 digits."""
        token = _issue_token(db_session)

        response = client.post(
            f"/api/v1/register/{token}", json=_payload(pincode="68202")
        )
        assert response.status_code == 422

    def test_replay_returns_410(self, client: TestClient, db_session: Session):
        """Second POST with same token → 410 consumed."""
        token = _issue_token(db_session)

        r1 = client.post(f"/api/v1/register/{token}", json=_payload(name="First"))
        assert r1.status_code == 200

        r2 = client.post(f"/api/v1/register/{token}", json=_payload(name="Second"))
        assert r2.status_code == 410

    def test_already_registered_returns_409(
        self, client: TestClient, db_session: Session
    ):
        """Phone already has a Customer → 409, token consumed."""
        customer = Customer(
            name="Existing User",
            primary_phone=PHONE,
            whatsapp_enabled=True,
            is_active=True,
            address_line_1="9 Old Road",
            city="Kochi",
            state="Kerala",
            pincode="682001",
        )
        db_session.add(customer)
        db_session.commit()

        token = _issue_token(db_session)

        response = client.post(
            f"/api/v1/register/{token}", json=_payload(name="New Attempt")
        )
        assert response.status_code == 409
        assert "already registered" in response.json()["detail"].lower()

        # Token consumed even though the request failed
        row = db_session.scalar(
            select(RegistrationToken).where(RegistrationToken.token == token)
        )
        assert row is not None
        assert row.consumed_at is not None

        # And no PendingRegistration was created
        reg = db_session.scalar(
            select(PendingRegistration).where(PendingRegistration.phone == PHONE)
        )
        assert reg is None

    def test_duplicate_awaiting_returns_success_message(
        self, client: TestClient, db_session: Session
    ):
        """Phone already has an awaiting_approval row → return existing id,
        don't create a duplicate."""
        token1 = _issue_token(db_session)
        r1 = client.post(f"/api/v1/register/{token1}", json=_payload(name="First Try"))
        assert r1.status_code == 200
        first_id = r1.json()["registration_id"]

        # Issue a fresh token and submit again
        token2 = _issue_token(db_session)
        r2 = client.post(f"/api/v1/register/{token2}", json=_payload(name="Second Try"))
        assert r2.status_code == 200
        # Should return the SAME registration_id (not a new row)
        assert r2.json()["registration_id"] == first_id

        # Only one row exists
        rows = db_session.scalars(
            select(PendingRegistration).where(PendingRegistration.phone == PHONE)
        ).all()
        assert len(rows) == 1

    def test_404_for_nonexistent_token(self, client: TestClient):
        response = client.post("/api/v1/register/fake-token", json=_payload())
        assert response.status_code == 404

    def test_410_for_expired_token(self, client: TestClient, db_session: Session):
        token = _issue_token(db_session)
        _expire_token(db_session, token)

        response = client.post(f"/api/v1/register/{token}", json=_payload())
        assert response.status_code == 410

    def test_deactivated_customer_may_register(
        self, client: TestClient, db_session: Session
    ):
        """Only ACTIVE customers block registration. The bot routes
        deactivated numbers to registration, so the form has to accept
        them — otherwise it's a dead end."""
        customer = Customer(
            name="Deactivated User",
            primary_phone=PHONE,
            whatsapp_enabled=True,
            is_active=False,
            address_line_1="9 Old Road",
            city="Kochi",
            state="Kerala",
            pincode="682001",
        )
        db_session.add(customer)
        db_session.commit()

        token = _issue_token(db_session)

        response = client.post(f"/api/v1/register/{token}", json=_payload())
        assert response.status_code == 200

        reg = db_session.scalar(
            select(PendingRegistration).where(PendingRegistration.phone == PHONE)
        )
        assert reg is not None
        assert reg.status == "awaiting_approval"
