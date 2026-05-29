"""Dashboard summary endpoint tests — Medium rigor.

Coverage:
  - empty state (no orders today)
  - status counts (pending / in_progress / cancelled)
  - revenue excludes cancelled
  - board groups by status, excludes cancelled
  - reference counts (active customers/products, unavailable)
  - auth required

Total: 7 tests.
"""

from datetime import date

import pytest


@pytest.fixture
def customer_id(client, auth_headers):
    r = client.post(
        "/api/v1/customers",
        json={
            "name": "Dash Customer",
            "primary_phone": "+919999800001",
            "address_line_1": "Test",
            "city": "Kochi",
            "state": "Kerala",
            "pincode": "682001",
        },
        headers=auth_headers,
    )
    return r.json()["id"]


@pytest.fixture
def category_id(client, auth_headers):
    r = client.post(
        "/api/v1/categories",
        json={"name": "savoury", "display_order": 0},
        headers=auth_headers,
    )
    return r.json()["id"]


@pytest.fixture
def product_id(client, auth_headers, category_id):
    r = client.post(
        "/api/v1/products",
        json={
            "name": "Veg Puff",
            "category_id": category_id,
            "unit_price": 20.00,
            "unit_label": "piece",
        },
        headers=auth_headers,
    )
    return r.json()["id"]


def _make_order(client, auth_headers, customer_id, product_id, qty=2, status=None):
    r = client.post(
        "/api/v1/orders",
        json={
            "customer_id": customer_id,
            "items": [{"product_id": product_id, "quantity": qty}],
        },
        headers=auth_headers,
    )
    oid = r.json()["id"]
    if status:
        client.patch(
            f"/api/v1/orders/{oid}/status",
            json={"status": status},
            headers=auth_headers,
        )
    return oid


def test_summary_empty_state(client, auth_headers):
    """No orders → zeros, empty board columns."""
    r = client.get("/api/v1/dashboard/summary", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["today_orders"] == 0
    assert body["pending"] == 0
    assert body["in_progress"] == 0
    assert body["cancelled_today"] == 0
    assert body["revenue_today"] == 0
    # Board has the four active-status keys, all empty
    assert set(body["board"].keys()) == {"received", "preparing", "ready", "delivering"}
    assert all(len(v) == 0 for v in body["board"].values())


def test_summary_status_counts(client, auth_headers, customer_id, product_id):
    # 2 received (pending), 1 preparing, 1 ready (both in_progress), 1 cancelled
    _make_order(client, auth_headers, customer_id, product_id)
    _make_order(client, auth_headers, customer_id, product_id)
    _make_order(client, auth_headers, customer_id, product_id, status="preparing")
    _make_order(client, auth_headers, customer_id, product_id, status="ready")
    _make_order(client, auth_headers, customer_id, product_id, status="cancelled")

    body = client.get("/api/v1/dashboard/summary", headers=auth_headers).json()
    assert body["today_orders"] == 5
    assert body["pending"] == 2
    assert body["in_progress"] == 2
    assert body["cancelled_today"] == 1


def test_summary_revenue_excludes_cancelled(
    client, auth_headers, customer_id, product_id
):
    # 2 active orders @ qty 2 @ ₹20 = ₹40 each → ₹80; plus 1 cancelled (excluded)
    _make_order(client, auth_headers, customer_id, product_id, qty=2)
    _make_order(client, auth_headers, customer_id, product_id, qty=2)
    _make_order(
        client, auth_headers, customer_id, product_id, qty=5, status="cancelled"
    )

    body = client.get("/api/v1/dashboard/summary", headers=auth_headers).json()
    assert body["revenue_today"] == 80.0


def test_summary_board_groups_and_excludes_cancelled(
    client, auth_headers, customer_id, product_id
):
    _make_order(client, auth_headers, customer_id, product_id)  # received
    _make_order(client, auth_headers, customer_id, product_id, status="preparing")
    _make_order(client, auth_headers, customer_id, product_id, status="cancelled")

    body = client.get("/api/v1/dashboard/summary", headers=auth_headers).json()
    assert len(body["board"]["received"]) == 1
    assert len(body["board"]["preparing"]) == 1
    # Cancelled is not on the board
    assert "cancelled" not in body["board"]
    # Board card shape
    card = body["board"]["received"][0]
    assert card["customer_name"] == "Dash Customer"
    assert "item_summary" in card
    assert card["status"] == "received"


def test_summary_reference_counts(client, auth_headers, customer_id, product_id):
    body = client.get("/api/v1/dashboard/summary", headers=auth_headers).json()
    # At least the one customer + one product we created
    assert body["active_customers"] >= 1
    assert body["active_products"] >= 1


def test_summary_unavailable_products(client, auth_headers, customer_id, category_id):
    # Create a product marked unavailable today
    client.post(
        "/api/v1/products",
        json={
            "name": "Weekend Special",
            "category_id": category_id,
            "unit_price": 50.00,
            "unit_label": "piece",
            "is_available_today": False,
        },
        headers=auth_headers,
    )
    body = client.get("/api/v1/dashboard/summary", headers=auth_headers).json()
    assert body["unavailable_products"] >= 1


def test_summary_requires_auth(client):
    r = client.get("/api/v1/dashboard/summary")
    assert r.status_code == 401
