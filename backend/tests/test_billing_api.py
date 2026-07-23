"""Tests for the /api/v1/billing endpoints.

Billing has no tables of its own, so these tests are mostly about the
two filters that decide what counts as revenue:

  is_draft = False      a cart in progress isn't revenue
  status != cancelled   a voided order isn't revenue, but still appears
                        on the invoice so the owner can see it

Everything is seeded directly rather than through the order service, so
each test states exactly the shape it needs.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from app.models.category import Category
from app.models.customer import Customer
from app.models.order import Order, OrderItem, OrderStatus
from app.models.product import Product
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

JAN = date(2026, 1, 10)
FEB = date(2026, 2, 10)


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def customer(db_session: Session) -> Customer:
    c = Customer(
        name="Billing Tester",
        primary_phone="+919888000111",
        whatsapp_enabled=True,
        is_active=True,
        address_line_1="12 Test Road",
        city="Kochi",
        state="Kerala",
        pincode="682020",
    )
    db_session.add(c)
    db_session.commit()
    db_session.refresh(c)
    return c


@pytest.fixture
def other_customer(db_session: Session) -> Customer:
    c = Customer(
        name="Second Tester",
        primary_phone="+919888000222",
        whatsapp_enabled=True,
        is_active=True,
        address_line_1="9 Other Road",
        city="Kochi",
        state="Kerala",
        pincode="682021",
    )
    db_session.add(c)
    db_session.commit()
    db_session.refresh(c)
    return c


@pytest.fixture
def product(db_session: Session) -> Product:
    cat = Category(name="billing_test_cat", display_order=99, is_active=True)
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
    """Seed one order with a single line item."""
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


RANGE = {"start": "2026-01-01", "end": "2026-12-31"}


# ============================================================
# GET /billing/summary
# ============================================================


class TestBillingSummary:
    def test_totals_billable_orders(
        self, client: TestClient, db_session, customer, product, auth_headers
    ):
        _order(db_session, customer, product, order_date=JAN, quantity=2)  # 40
        _order(db_session, customer, product, order_date=FEB, quantity=3)  # 60

        r = client.get("/api/v1/billing/summary", params=RANGE, headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert data["revenue"] == 100.0
        assert data["order_count"] == 2
        assert data["customer_count"] == 1
        assert data["cancelled_count"] == 0

    def test_excludes_cancelled_from_revenue(
        self, client: TestClient, db_session, customer, product, auth_headers
    ):
        """Cancelled orders are counted separately, never in revenue."""
        _order(db_session, customer, product, order_date=JAN, quantity=2)  # 40
        _order(
            db_session,
            customer,
            product,
            order_date=JAN,
            quantity=5,
            status=OrderStatus.cancelled,
        )

        r = client.get("/api/v1/billing/summary", params=RANGE, headers=auth_headers)
        data = r.json()
        assert data["revenue"] == 40.0
        assert data["order_count"] == 1
        assert data["cancelled_count"] == 1

    def test_excludes_drafts(
        self, client: TestClient, db_session, customer, product, auth_headers
    ):
        """A draft is a cart the customer never placed."""
        _order(db_session, customer, product, order_date=JAN, quantity=2)  # 40
        _order(db_session, customer, product, order_date=JAN, quantity=9, is_draft=True)

        r = client.get("/api/v1/billing/summary", params=RANGE, headers=auth_headers)
        data = r.json()
        assert data["revenue"] == 40.0
        assert data["order_count"] == 1
        # Drafts don't show up as cancelled either — they're invisible
        assert data["cancelled_count"] == 0

    def test_counts_distinct_customers(
        self,
        client: TestClient,
        db_session,
        customer,
        other_customer,
        product,
        auth_headers,
    ):
        _order(db_session, customer, product, order_date=JAN)
        _order(db_session, customer, product, order_date=FEB)
        _order(db_session, other_customer, product, order_date=JAN)

        r = client.get("/api/v1/billing/summary", params=RANGE, headers=auth_headers)
        assert r.json()["customer_count"] == 2

    def test_respects_date_range(
        self, client: TestClient, db_session, customer, product, auth_headers
    ):
        _order(db_session, customer, product, order_date=JAN, quantity=2)  # 40
        _order(db_session, customer, product, order_date=FEB, quantity=3)  # 60

        r = client.get(
            "/api/v1/billing/summary",
            params={"start": "2026-01-01", "end": "2026-01-31"},
            headers=auth_headers,
        )
        assert r.json()["revenue"] == 40.0

    def test_empty_range_returns_zeros(self, client: TestClient, auth_headers):
        r = client.get("/api/v1/billing/summary", params=RANGE, headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert data["revenue"] == 0
        assert data["order_count"] == 0
        assert data["customer_count"] == 0

    def test_inverted_range_returns_422(self, client: TestClient, auth_headers):
        """Silently returning zero rows would read as 'no orders' rather
        than 'you typed the dates backwards'."""
        r = client.get(
            "/api/v1/billing/summary",
            params={"start": "2026-12-31", "end": "2026-01-01"},
            headers=auth_headers,
        )
        assert r.status_code == 422

    def test_requires_auth(self, client: TestClient):
        r = client.get("/api/v1/billing/summary", params=RANGE)
        assert r.status_code == 401


# ============================================================
# GET /billing/customers
# ============================================================


class TestBillingCustomers:
    def test_lists_customers_by_total_desc(
        self,
        client: TestClient,
        db_session,
        customer,
        other_customer,
        product,
        auth_headers,
    ):
        _order(db_session, customer, product, order_date=JAN, quantity=1)  # 20
        _order(db_session, other_customer, product, order_date=JAN, quantity=5)  # 100

        r = client.get("/api/v1/billing/customers", params=RANGE, headers=auth_headers)
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) == 2
        assert items[0]["customer_name"] == "Second Tester"
        assert items[0]["total"] == 100.0
        assert items[1]["total"] == 20.0

    def test_invoice_count_is_distinct_dates(
        self, client: TestClient, db_session, customer, product, auth_headers
    ):
        """Three orders across two days is two invoices, not three."""
        _order(db_session, customer, product, order_date=JAN)
        _order(db_session, customer, product, order_date=JAN)
        _order(db_session, customer, product, order_date=FEB)

        r = client.get("/api/v1/billing/customers", params=RANGE, headers=auth_headers)
        row = r.json()["items"][0]
        assert row["order_count"] == 3
        assert row["invoice_count"] == 2
        assert row["first_order_date"] == "2026-01-10"
        assert row["last_order_date"] == "2026-02-10"

    def test_omits_customers_with_no_billable_orders(
        self,
        client: TestClient,
        db_session,
        customer,
        other_customer,
        product,
        auth_headers,
    ):
        _order(db_session, customer, product, order_date=JAN)
        _order(
            db_session,
            other_customer,
            product,
            order_date=JAN,
            status=OrderStatus.cancelled,
        )

        r = client.get("/api/v1/billing/customers", params=RANGE, headers=auth_headers)
        items = r.json()["items"]
        assert len(items) == 1
        assert items[0]["customer_name"] == "Billing Tester"

    def test_requires_auth(self, client: TestClient):
        r = client.get("/api/v1/billing/customers", params=RANGE)
        assert r.status_code == 401


# ============================================================
# GET /billing/customers/{id}/dates
# ============================================================


class TestBillingCustomerDates:
    def test_lists_dates_most_recent_first(
        self, client: TestClient, db_session, customer, product, auth_headers
    ):
        _order(db_session, customer, product, order_date=JAN, quantity=1)  # 20
        _order(db_session, customer, product, order_date=FEB, quantity=2)  # 40
        _order(db_session, customer, product, order_date=FEB, quantity=1)  # 20

        r = client.get(
            f"/api/v1/billing/customers/{customer.id}/dates",
            params=RANGE,
            headers=auth_headers,
        )
        assert r.status_code == 200
        data = r.json()
        assert data["customer"]["name"] == "Billing Tester"
        items = data["items"]
        assert len(items) == 2
        # Most recent first, and the two Feb orders combine
        assert items[0]["order_date"] == "2026-02-10"
        assert items[0]["order_count"] == 2
        assert items[0]["total"] == 60.0
        assert items[1]["order_date"] == "2026-01-10"

    def test_invoice_number_format(
        self, client: TestClient, db_session, customer, product, auth_headers
    ):
        _order(db_session, customer, product, order_date=JAN)

        r = client.get(
            f"/api/v1/billing/customers/{customer.id}/dates",
            params=RANGE,
            headers=auth_headers,
        )
        expected = f"INV-20260110-{str(customer.id)[:8]}"
        assert r.json()["items"][0]["invoice_number"] == expected

    def test_404_for_unknown_customer(self, client: TestClient, auth_headers):
        r = client.get(
            f"/api/v1/billing/customers/{uuid4()}/dates",
            params=RANGE,
            headers=auth_headers,
        )
        assert r.status_code == 404

    def test_requires_auth(self, client: TestClient, customer):
        r = client.get(f"/api/v1/billing/customers/{customer.id}/dates", params=RANGE)
        assert r.status_code == 401


# ============================================================
# GET /billing/customers/{id}/invoice/{date}
# ============================================================


class TestInvoice:
    def test_combines_multiple_orders_on_one_day(
        self, client: TestClient, db_session, customer, product, auth_headers
    ):
        """The whole reason invoices are per-day rather than per-order."""
        _order(db_session, customer, product, order_date=JAN, quantity=2)  # 40
        _order(db_session, customer, product, order_date=JAN, quantity=3)  # 60

        r = client.get(
            f"/api/v1/billing/customers/{customer.id}/invoice/2026-01-10",
            headers=auth_headers,
        )
        assert r.status_code == 200
        data = r.json()
        assert len(data["orders"]) == 2
        assert data["order_count"] == 2
        assert data["total"] == 100.0
        assert data["invoice_number"] == f"INV-20260110-{str(customer.id)[:8]}"

    def test_carries_snapshotted_line_items(
        self, client: TestClient, db_session, customer, product, auth_headers
    ):
        _order(db_session, customer, product, order_date=JAN, quantity=2)

        r = client.get(
            f"/api/v1/billing/customers/{customer.id}/invoice/2026-01-10",
            headers=auth_headers,
        )
        line = r.json()["orders"][0]["items"][0]
        assert line["product_name"] == "Test Puff"
        assert line["unit_price"] == 20.0
        assert line["unit_label"] == "piece"
        assert line["quantity"] == 2
        assert line["subtotal"] == 40.0

    def test_shows_cancelled_but_excludes_from_total(
        self, client: TestClient, db_session, customer, product, auth_headers
    ):
        """The owner should see what was ordered and voided."""
        _order(db_session, customer, product, order_date=JAN, quantity=2)  # 40
        _order(
            db_session,
            customer,
            product,
            order_date=JAN,
            quantity=5,
            status=OrderStatus.cancelled,
        )

        r = client.get(
            f"/api/v1/billing/customers/{customer.id}/invoice/2026-01-10",
            headers=auth_headers,
        )
        data = r.json()
        assert len(data["orders"]) == 2
        assert data["order_count"] == 1
        assert data["cancelled_count"] == 1
        assert data["total"] == 40.0
        cancelled = [o for o in data["orders"] if o["is_cancelled"]]
        assert len(cancelled) == 1

    def test_omits_drafts_entirely(
        self, client: TestClient, db_session, customer, product, auth_headers
    ):
        """Unlike cancelled orders, a draft was never placed — it
        shouldn't appear on the invoice at all."""
        _order(db_session, customer, product, order_date=JAN, quantity=2)
        _order(db_session, customer, product, order_date=JAN, quantity=9, is_draft=True)

        r = client.get(
            f"/api/v1/billing/customers/{customer.id}/invoice/2026-01-10",
            headers=auth_headers,
        )
        assert len(r.json()["orders"]) == 1

    def test_includes_business_and_customer_blocks(
        self, client: TestClient, db_session, customer, product, auth_headers
    ):
        _order(db_session, customer, product, order_date=JAN)

        r = client.get(
            f"/api/v1/billing/customers/{customer.id}/invoice/2026-01-10",
            headers=auth_headers,
        )
        data = r.json()
        assert data["business"]["name"]  # from config, always set
        assert data["customer"]["name"] == "Billing Tester"
        assert data["customer"]["address_line_1"] == "12 Test Road"
        assert data["customer"]["pincode"] == "682020"

    def test_404_when_no_orders_that_day(
        self, client: TestClient, db_session, customer, product, auth_headers
    ):
        _order(db_session, customer, product, order_date=JAN)

        r = client.get(
            f"/api/v1/billing/customers/{customer.id}/invoice/2026-03-15",
            headers=auth_headers,
        )
        assert r.status_code == 404

    def test_404_for_unknown_customer(self, client: TestClient, auth_headers):
        r = client.get(
            f"/api/v1/billing/customers/{uuid4()}/invoice/2026-01-10",
            headers=auth_headers,
        )
        assert r.status_code == 404

    def test_requires_auth(self, client: TestClient, customer):
        r = client.get(f"/api/v1/billing/customers/{customer.id}/invoice/2026-01-10")
        assert r.status_code == 401
