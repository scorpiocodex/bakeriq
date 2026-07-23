"""Tests for the customer-facing invoice link.

Three things under test, and they fail in different ways:

  1. token_service — the 'invoice' kind exists, gets a longer TTL than
     cart kinds, and nothing consumes it
  2. GET /api/v1/invoice/{token} — token-authed, resolves "latest",
     404s on everything else
  3. customer_handler — the Invoice button and keywords return a CTA
     card, or a graceful message when there's nothing to bill

"Latest" means the day of the customer's most recent *billable* order.
Drafts and cancelled orders must not drag the invoice date forward to a
day that would render as empty or void-only.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from app.models.category import Category
from app.models.customer import Customer
from app.models.order import Order, OrderItem, OrderStatus
from app.models.product import Product
from app.models.web_session_token import WebSessionToken
from app.services import customer_handler, token_service
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

OLD = date(2026, 3, 1)
RECENT = date(2026, 3, 20)


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def customer(db_session: Session) -> Customer:
    c = Customer(
        name="Invoice Tester",
        primary_phone="+919888444001",
        whatsapp_enabled=True,
        is_active=True,
        address_line_1="5 Invoice Lane",
        city="Kochi",
        state="Kerala",
        pincode="682020",
    )
    db_session.add(c)
    db_session.commit()
    db_session.refresh(c)
    return c


@pytest.fixture
def product(db_session: Session) -> Product:
    cat = Category(name="invoice_test_cat", display_order=99, is_active=True)
    db_session.add(cat)
    db_session.flush()

    p = Product(
        name="Test Puff",
        category_id=cat.id,
        unit_price=Decimal("20.00"),
        unit_label="piece",
        is_available_today=True,
        is_active=True,
    )
    db_session.add(p)
    db_session.commit()
    db_session.refresh(p)
    return p


def _order(
    db_session: Session,
    customer: Customer,
    product: Product,
    *,
    order_date: date,
    quantity: int = 2,
    status: OrderStatus = OrderStatus.received,
    is_draft: bool = False,
) -> Order:
    subtotal = product.unit_price * quantity
    order = Order(
        customer_id=customer.id,
        status=status,
        is_draft=is_draft,
        order_date=order_date,
        total_amount=subtotal,
    )
    db_session.add(order)
    db_session.flush()
    db_session.add(
        OrderItem(
            order_id=order.id,
            product_id=product.id,
            product_name=product.name,
            unit_price=product.unit_price,
            unit_label=product.unit_label,
            quantity=quantity,
            subtotal=subtotal,
        )
    )
    db_session.commit()
    db_session.refresh(order)
    return order


def _invoice_token(db_session: Session, customer: Customer) -> str:
    row = token_service.issue_token(db_session, customer=customer, kind="invoice")
    db_session.commit()
    return row.token


# ============================================================
# token_service — the invoice kind
# ============================================================


class TestInvoiceTokenKind:
    def test_issues_invoice_token(self, db_session: Session, customer):
        row = token_service.issue_token(db_session, customer=customer, kind="invoice")
        db_session.commit()
        assert row.kind == "invoice"
        assert row.customer_id == customer.id
        assert row.consumed_at is None

    def test_invoice_ttl_longer_than_cart(self, db_session: Session, customer):
        """A cart should expire so abandoned carts clear. An invoice is a
        document the customer may reopen later in the day."""
        cart = token_service.issue_token(db_session, customer=customer, kind="new")
        invoice = token_service.issue_token(
            db_session, customer=customer, kind="invoice"
        )
        db_session.commit()
        assert invoice.expires_at > cart.expires_at

    def test_rejects_unknown_kind(self, db_session: Session, customer):
        with pytest.raises(ValueError):
            token_service.issue_token(db_session, customer=customer, kind="nonsense")

    def test_validates_like_any_other_kind(self, db_session: Session, customer):
        token = _invoice_token(db_session, customer)
        row = token_service.validate_token(db_session, token)
        assert row is not None
        assert row.kind == "invoice"


# ============================================================
# GET /api/v1/invoice/{token}
# ============================================================


class TestInvoiceEndpoint:
    def test_returns_latest_invoice(
        self, client: TestClient, db_session, customer, product
    ):
        _order(db_session, customer, product, order_date=OLD, quantity=1)  # 20
        _order(db_session, customer, product, order_date=RECENT, quantity=3)  # 60
        token = _invoice_token(db_session, customer)

        r = client.get(f"/api/v1/invoice/{token}")
        assert r.status_code == 200
        data = r.json()
        assert data["invoice_date"] == "2026-03-20"
        assert data["total"] == 60.0

    def test_combines_multiple_orders_that_day(
        self, client: TestClient, db_session, customer, product
    ):
        _order(db_session, customer, product, order_date=RECENT, quantity=2)  # 40
        _order(db_session, customer, product, order_date=RECENT, quantity=3)  # 60
        token = _invoice_token(db_session, customer)

        r = client.get(f"/api/v1/invoice/{token}")
        data = r.json()
        assert len(data["orders"]) == 2
        assert data["total"] == 100.0

    def test_draft_does_not_become_latest(
        self, client: TestClient, db_session, customer, product
    ):
        """A cart in progress on a later date shouldn't drag the invoice
        forward to a day that would render empty."""
        _order(db_session, customer, product, order_date=OLD, quantity=1)  # 20
        _order(
            db_session,
            customer,
            product,
            order_date=RECENT,
            quantity=9,
            is_draft=True,
        )
        token = _invoice_token(db_session, customer)

        r = client.get(f"/api/v1/invoice/{token}")
        data = r.json()
        assert data["invoice_date"] == "2026-03-01"
        assert data["total"] == 20.0

    def test_cancelled_does_not_become_latest(
        self, client: TestClient, db_session, customer, product
    ):
        """An invoice listing only a voided order isn't one the customer
        wants to see."""
        _order(db_session, customer, product, order_date=OLD, quantity=1)  # 20
        _order(
            db_session,
            customer,
            product,
            order_date=RECENT,
            quantity=5,
            status=OrderStatus.cancelled,
        )
        token = _invoice_token(db_session, customer)

        r = client.get(f"/api/v1/invoice/{token}")
        assert r.json()["invoice_date"] == "2026-03-01"

    def test_includes_business_details(
        self, client: TestClient, db_session, customer, product
    ):
        _order(db_session, customer, product, order_date=RECENT)
        token = _invoice_token(db_session, customer)

        r = client.get(f"/api/v1/invoice/{token}")
        assert r.json()["business"]["name"]

    def test_404_when_customer_never_ordered(
        self, client: TestClient, db_session, customer
    ):
        token = _invoice_token(db_session, customer)
        r = client.get(f"/api/v1/invoice/{token}")
        assert r.status_code == 404

    def test_404_for_unknown_token(self, client: TestClient):
        r = client.get("/api/v1/invoice/completely-made-up-token")
        assert r.status_code == 404

    def test_404_for_cart_token(
        self, client: TestClient, db_session, customer, product
    ):
        """A cart token identifies the same customer but grants a
        different capability. Kind is part of the credential."""
        _order(db_session, customer, product, order_date=RECENT)
        row = token_service.issue_token(db_session, customer=customer, kind="new")
        db_session.commit()

        r = client.get(f"/api/v1/invoice/{row.token}")
        assert r.status_code == 404

    def test_404_for_expired_token(
        self, client: TestClient, db_session, customer, product
    ):
        _order(db_session, customer, product, order_date=RECENT)
        token = _invoice_token(db_session, customer)

        row = db_session.scalar(
            select(WebSessionToken).where(WebSessionToken.token == token)
        )
        row.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        db_session.commit()

        r = client.get(f"/api/v1/invoice/{token}")
        assert r.status_code == 404

    def test_reopenable(self, client: TestClient, db_session, customer, product):
        """Nothing consumes an invoice token — the customer may come back
        to it. This is the one place the cart flow's consume-on-use
        behaviour would be wrong."""
        _order(db_session, customer, product, order_date=RECENT)
        token = _invoice_token(db_session, customer)

        assert client.get(f"/api/v1/invoice/{token}").status_code == 200
        assert client.get(f"/api/v1/invoice/{token}").status_code == 200

    def test_needs_no_jwt(self, client: TestClient, db_session, customer, product):
        """Unlike /billing, this is customer-facing — the token is the
        whole credential."""
        _order(db_session, customer, product, order_date=RECENT)
        token = _invoice_token(db_session, customer)

        r = client.get(f"/api/v1/invoice/{token}")
        assert r.status_code == 200


# ============================================================
# customer_handler — the Invoice button
# ============================================================


class TestInvoiceHandler:
    def test_button_returns_link_card(self, db_session, customer, product):
        _order(db_session, customer, product, order_date=RECENT)

        replies = customer_handler.handle_customer_message(
            db_session, customer, "Invoice"
        )
        assert replies is not None
        assert len(replies) == 1

        # An invoice token was minted for this customer
        row = db_session.scalar(
            select(WebSessionToken).where(
                WebSessionToken.customer_id == customer.id,
                WebSessionToken.kind == "invoice",
            )
        )
        assert row is not None

    @pytest.mark.parametrize("word", ["invoice", "bill", "receipt", "my bill"])
    def test_keywords_work_too(self, db_session, customer, product, word):
        """Customers who've been typing rather than tapping shouldn't
        have to discover the button."""
        _order(db_session, customer, product, order_date=RECENT)

        replies = customer_handler.handle_customer_message(db_session, customer, word)
        assert replies is not None
        assert len(replies) == 1

    def test_no_orders_gets_message_not_dead_link(self, db_session, customer):
        """Issuing a link that resolves to 404 would be worse than saying
        so up front."""
        replies = customer_handler.handle_customer_message(
            db_session, customer, "invoice"
        )
        assert replies is not None
        assert len(replies) == 2  # explanation + nav card
        assert replies[0].body is not None
        assert "invoice" in replies[0].body.lower()

        # And no token was wasted
        row = db_session.scalar(
            select(WebSessionToken).where(
                WebSessionToken.customer_id == customer.id,
                WebSessionToken.kind == "invoice",
            )
        )
        assert row is None

    def test_only_cancelled_orders_counts_as_none(self, db_session, customer, product):
        """A cancelled order isn't something to invoice."""
        _order(
            db_session,
            customer,
            product,
            order_date=RECENT,
            status=OrderStatus.cancelled,
        )

        replies = customer_handler.handle_customer_message(
            db_session, customer, "invoice"
        )
        assert len(replies) == 2  # the "no invoice" path
