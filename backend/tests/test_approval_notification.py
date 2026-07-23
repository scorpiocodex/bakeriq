"""Tests for the approval notification.

The webform tells the customer "you'll get a WhatsApp message once the
bakery owner approves you", and the bot's awaiting-approval reply makes
the same promise. These cover the send that makes both true.

The notification itself is muted by the autouse fixture in conftest, so
these tests patch it back in with a spy rather than letting it through
to Twilio.
"""

from __future__ import annotations

import pytest
from app.models.customer import Customer
from app.models.pending_registration import PendingRegistration
from app.services import customer_notification_service, template_replies
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session


@pytest.fixture
def spy(monkeypatch):
    """Record calls to notify_approved instead of sending.

    Overrides the conftest mute — which is autouse and would otherwise
    swallow the call we're trying to observe.
    """
    calls = []

    def _record(db, customer):
        calls.append(customer)

    monkeypatch.setattr(customer_notification_service, "notify_approved", _record)
    # The endpoint resolves the attribute at call time off the module, so
    # patching the module is enough — no need to touch the import site.
    return calls


def _pending(db_session: Session, phone: str = "+919888777555") -> PendingRegistration:
    reg = PendingRegistration(
        phone=phone,
        name="Approved Person",
        address_line_1="7 Welcome Road",
        city="Kochi",
        state="Kerala",
        pincode="682020",
        status="awaiting_approval",
    )
    db_session.add(reg)
    db_session.commit()
    db_session.refresh(reg)
    return reg


class TestApprovalNotification:
    def test_approving_notifies_the_customer(
        self, client: TestClient, db_session, auth_headers, spy
    ):
        reg = _pending(db_session)

        r = client.post(f"/api/v1/approvals/{reg.id}/approve", headers=auth_headers)
        assert r.status_code == 200

        assert len(spy) == 1
        assert spy[0].name == "Approved Person"
        assert spy[0].primary_phone == "+919888777555"

    def test_notified_customer_is_the_created_one(
        self, client: TestClient, db_session, auth_headers, spy
    ):
        """The message has to go to the Customer row, not the pending row
        — they're different objects and only one has an id the rest of the
        system knows about."""
        reg = _pending(db_session)

        r = client.post(f"/api/v1/approvals/{reg.id}/approve", headers=auth_headers)
        customer_id = r.json()["customer_id"]

        assert str(spy[0].id) == customer_id

    def test_rejecting_does_not_notify(
        self, client: TestClient, db_session, auth_headers, spy
    ):
        """Nothing promised the customer a rejection message, and an
        unprompted one is worse than the polite decline the bot gives if
        they message again."""
        reg = _pending(db_session)

        r = client.post(
            f"/api/v1/approvals/{reg.id}/reject",
            headers=auth_headers,
            json={"reason": "duplicate"},
        )
        assert r.status_code == 200
        assert spy == []

    def test_second_approve_does_not_notify_again(
        self, client: TestClient, db_session, auth_headers, spy
    ):
        """A 409 shouldn't send a second welcome."""
        reg = _pending(db_session)

        client.post(f"/api/v1/approvals/{reg.id}/approve", headers=auth_headers)
        r2 = client.post(f"/api/v1/approvals/{reg.id}/approve", headers=auth_headers)
        assert r2.status_code == 409
        assert len(spy) == 1

    def test_reactivation_notifies_too(
        self, client: TestClient, db_session, auth_headers, spy
    ):
        """A returning customer whose account was deactivated is approved
        by reactivating the existing row. They should still hear about
        it."""
        phone = "+919888777556"
        old = Customer(
            name="Returning Person",
            primary_phone=phone,
            whatsapp_enabled=True,
            is_active=False,
            address_line_1="1 Old Road",
            city="Kochi",
            state="Kerala",
            pincode="682001",
        )
        db_session.add(old)
        db_session.commit()

        reg = _pending(db_session, phone=phone)
        r = client.post(f"/api/v1/approvals/{reg.id}/approve", headers=auth_headers)
        assert r.status_code == 200
        assert len(spy) == 1
        assert spy[0].primary_phone == phone


class TestApprovedReply:
    def test_template_when_sid_set(self, monkeypatch):
        from app.core.config import settings

        monkeypatch.setattr(settings, "CONTENT_SID_APPROVED", "HX_test_approved")

        reply = template_replies.approved_reply("Anita Menon")
        assert reply.is_template is True
        assert reply.content_sid == "HX_test_approved"
        # First name only — the greeting card does the same
        assert reply.content_variables == {"1": "Anita"}

    def test_text_fallback_when_sid_unset(self, monkeypatch):
        from app.core.config import settings

        monkeypatch.setattr(settings, "CONTENT_SID_APPROVED", None)

        reply = template_replies.approved_reply("Anita Menon")
        assert reply.is_template is False
        assert reply.body is not None
        assert "Anita" in reply.body

    def test_handles_blank_name(self, monkeypatch):
        """Name is required on the webform, but a Customer created through
        the dashboard could in principle have something odd."""
        from app.core.config import settings

        monkeypatch.setattr(settings, "CONTENT_SID_APPROVED", None)

        reply = template_replies.approved_reply("")
        assert reply.body is not None
        assert "there" in reply.body

    def test_log_body_is_readable(self, monkeypatch):
        """The admin transcript viewer should show prose, not a SID."""
        from app.core.config import settings

        monkeypatch.setattr(settings, "CONTENT_SID_APPROVED", "HX_test_approved")

        reply = template_replies.approved_reply("Anita Menon")
        assert reply.log_body is not None
        assert "Anita" in reply.log_body
        assert "approved" in reply.log_body.lower()
