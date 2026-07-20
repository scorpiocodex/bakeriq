"""Tests for the /api/v1/approvals endpoints.

Covers:
  - GET  /approvals        — list awaiting
  - GET  /approvals/count  — sidebar badge polling
  - POST /approvals/{id}/approve — creates Customer, flips status
  - POST /approvals/{id}/reject  — flips status, keeps row

Auth is via the same JWT-Depends pattern used across the admin API.
Fixtures come from tests/conftest.py:
  - client: TestClient with dependency-overridden get_db
  - db_session: the same test DB session
  - auth_headers: fixture that returns {'Authorization': 'Bearer ...'}
    for a seeded owner user (matches the pattern in test_cart_api.py
    and the other admin API tests)

If your project's fixture is named differently, adjust the import.
"""

from __future__ import annotations

from uuid import uuid4

from app.models.customer import Customer
from app.models.pending_registration import PendingRegistration
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

# ============================================================
# Helpers
# ============================================================


def _make_pending(
    db_session: Session, phone: str, name: str = "Test"
) -> PendingRegistration:
    """Insert a PendingRegistration row directly (bypassing token flow)."""
    reg = PendingRegistration(
        phone=phone,
        name=name,
        address_line_1="12 Test Road",
        city="Kochi",
        state="Kerala",
        pincode="682020",
        status="awaiting_approval",
    )
    db_session.add(reg)
    db_session.commit()
    db_session.refresh(reg)
    return reg


# ============================================================
# GET /api/v1/approvals — list
# ============================================================


class TestListApprovals:
    def test_returns_awaiting_rows(
        self, client: TestClient, db_session: Session, auth_headers
    ):
        _make_pending(db_session, phone="+911111111111", name="First")
        _make_pending(db_session, phone="+911111111112", name="Second")

        r = client.get("/api/v1/approvals", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert data["total"] == 2
        assert len(data["items"]) == 2
        names = [item["name"] for item in data["items"]]
        assert "First" in names
        assert "Second" in names

    def test_excludes_approved_and_rejected(
        self, client: TestClient, db_session: Session, auth_headers
    ):
        """Only awaiting_approval rows should appear."""
        reg1 = _make_pending(db_session, phone="+911111111121", name="Awaiting")
        reg2 = _make_pending(db_session, phone="+911111111122", name="Approved")
        reg2.status = "approved"
        reg3 = _make_pending(db_session, phone="+911111111123", name="Rejected")
        reg3.status = "rejected"
        db_session.commit()

        r = client.get("/api/v1/approvals", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert data["total"] == 1
        assert data["items"][0]["name"] == "Awaiting"

    def test_requires_auth(self, client: TestClient):
        """No JWT → 401."""
        r = client.get("/api/v1/approvals")
        assert r.status_code == 401


# ============================================================
# GET /api/v1/approvals/count
# ============================================================


class TestApprovalsCount:
    def test_returns_count(self, client: TestClient, db_session: Session, auth_headers):
        _make_pending(db_session, phone="+911111111131")
        _make_pending(db_session, phone="+911111111132")
        _make_pending(db_session, phone="+911111111133")

        r = client.get("/api/v1/approvals/count", headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["count"] == 3

    def test_requires_auth(self, client: TestClient):
        r = client.get("/api/v1/approvals/count")
        assert r.status_code == 401


# ============================================================
# POST /approvals/{id}/approve
# ============================================================


class TestApproveRegistration:
    def test_creates_customer_and_flips_status(
        self, client: TestClient, db_session: Session, auth_headers
    ):
        reg = _make_pending(
            db_session,
            phone="+911111111141",
            name="Approve Me",
        )

        r = client.post(f"/api/v1/approvals/{reg.id}/approve", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert "customer_id" in data
        assert data["message"].startswith("Approved")

        # Verify Customer row exists with structured address
        customer = db_session.scalar(
            select(Customer).where(Customer.primary_phone == "+911111111141")
        )
        assert customer is not None
        assert customer.name == "Approve Me"
        assert customer.address_line_1 == "12 Test Road"
        assert customer.city == "Kochi"

        # Verify PendingRegistration status flipped and customer_id set
        db_session.refresh(reg)
        assert reg.status == "approved"
        assert reg.customer_id == customer.id

    def test_second_approve_returns_409(
        self, client: TestClient, db_session: Session, auth_headers
    ):
        """Idempotency guard: re-approving is a 409, not a duplicate Customer."""
        reg = _make_pending(db_session, phone="+911111111142")

        r1 = client.post(f"/api/v1/approvals/{reg.id}/approve", headers=auth_headers)
        assert r1.status_code == 200

        r2 = client.post(f"/api/v1/approvals/{reg.id}/approve", headers=auth_headers)
        assert r2.status_code == 409
        assert "already approved" in r2.json()["detail"]

    def test_404_for_nonexistent(self, client: TestClient, auth_headers):
        fake_id = uuid4()
        r = client.post(f"/api/v1/approvals/{fake_id}/approve", headers=auth_headers)
        assert r.status_code == 404

    def test_requires_auth(self, client: TestClient, db_session: Session):
        reg = _make_pending(db_session, phone="+911111111143")
        r = client.post(f"/api/v1/approvals/{reg.id}/approve")
        assert r.status_code == 401


# ============================================================
# POST /approvals/{id}/reject
# ============================================================


class TestRejectRegistration:
    def test_flips_status_no_customer_created(
        self, client: TestClient, db_session: Session, auth_headers
    ):
        reg = _make_pending(
            db_session,
            phone="+911111111151",
            name="Reject Me",
        )

        r = client.post(
            f"/api/v1/approvals/{reg.id}/reject",
            headers=auth_headers,
            json={"reason": "Testing rejection"},
        )
        assert r.status_code == 200

        db_session.refresh(reg)
        assert reg.status == "rejected"

        # Ensure no Customer was created
        customer = db_session.scalar(
            select(Customer).where(Customer.primary_phone == "+911111111151")
        )
        assert customer is None

    def test_reason_optional(
        self, client: TestClient, db_session: Session, auth_headers
    ):
        """Reject with no reason should work — for 'obvious garbage' cases."""
        reg = _make_pending(db_session, phone="+911111111152")

        r = client.post(
            f"/api/v1/approvals/{reg.id}/reject",
            headers=auth_headers,
            json={},
        )
        assert r.status_code == 200

    def test_second_reject_returns_409(
        self, client: TestClient, db_session: Session, auth_headers
    ):
        reg = _make_pending(db_session, phone="+911111111153")

        r1 = client.post(
            f"/api/v1/approvals/{reg.id}/reject",
            headers=auth_headers,
            json={},
        )
        assert r1.status_code == 200

        r2 = client.post(
            f"/api/v1/approvals/{reg.id}/reject",
            headers=auth_headers,
            json={},
        )
        assert r2.status_code == 409
