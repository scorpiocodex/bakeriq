"""Order endpoint tests — Medium rigor.

Coverage:
  Create (4): success, snapshot integrity, total computation, empty/invalid
  Status (4): forward, cancel from any, no-reactivate-cancelled, bad value
  Get/List (4): detail, list compact rows, status filter, customer filter
  Update (2): replace items + recompute total, edit notes only
  Prefill (2): from template, skips inactive
  Validation (1): auth required

Total: 17 tests.
"""

import pytest


@pytest.fixture
def customer_id(client, auth_headers):
    r = client.post(
        "/api/v1/customers",
        json={
            "name": "Order Customer",
            "primary_phone": "+919999911111",
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
def product_ids(client, auth_headers, category_id):
    """Two products. Returns ((id1, price1), (id2, price2))."""
    out = []
    for name, price in [("Veg Puff", 18.00), ("Egg Puff", 21.00)]:
        r = client.post(
            "/api/v1/products",
            json={
                "name": name,
                "category_id": category_id,
                "unit_price": price,
                "unit_label": "piece",
            },
            headers=auth_headers,
        )
        out.append((r.json()["id"], price))
    return tuple(out)


# === CREATE ===


def test_create_order_succeeds(client, auth_headers, customer_id, product_ids):
    (p1, _), (p2, _) = product_ids
    r = client.post(
        "/api/v1/orders",
        json={
            "customer_id": customer_id,
            "items": [
                {"product_id": p1, "quantity": 3},
                {"product_id": p2, "quantity": 2},
            ],
        },
        headers=auth_headers,
    )
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "received"
    assert len(body["items"]) == 2
    assert body["customer"]["id"] == customer_id


def test_create_order_snapshots_product_details(
    client, auth_headers, customer_id, product_ids
):
    (p1, price1), _ = product_ids
    r = client.post(
        "/api/v1/orders",
        json={"customer_id": customer_id, "items": [{"product_id": p1, "quantity": 3}]},
        headers=auth_headers,
    )
    item = r.json()["items"][0]
    assert item["product_name"] == "Veg Puff"
    assert float(item["unit_price"]) == price1
    assert item["unit_label"] == "piece"
    assert item["quantity"] == 3
    assert float(item["subtotal"]) == price1 * 3


def test_create_order_computes_total(client, auth_headers, customer_id, product_ids):
    (p1, price1), (p2, price2) = product_ids
    r = client.post(
        "/api/v1/orders",
        json={
            "customer_id": customer_id,
            "items": [
                {"product_id": p1, "quantity": 3},
                {"product_id": p2, "quantity": 2},
            ],
        },
        headers=auth_headers,
    )
    expected = price1 * 3 + price2 * 2
    assert float(r.json()["total_amount"]) == expected


def test_create_order_rejects_empty_items(client, auth_headers, customer_id):
    r = client.post(
        "/api/v1/orders",
        json={"customer_id": customer_id, "items": []},
        headers=auth_headers,
    )
    assert r.status_code == 422


def test_snapshot_survives_price_change(client, auth_headers, customer_id, product_ids):
    """The core snapshot guarantee: changing a product's price later does
    NOT alter an existing order."""
    (p1, price1), _ = product_ids
    r = client.post(
        "/api/v1/orders",
        json={"customer_id": customer_id, "items": [{"product_id": p1, "quantity": 2}]},
        headers=auth_headers,
    )
    order_id = r.json()["id"]
    original_total = float(r.json()["total_amount"])

    # Change the product price
    client.put(
        f"/api/v1/products/{p1}",
        json={"unit_price": 999.00},
        headers=auth_headers,
    )

    # Re-fetch the order — total and item price must be unchanged
    r2 = client.get(f"/api/v1/orders/{order_id}", headers=auth_headers)
    assert float(r2.json()["total_amount"]) == original_total
    assert float(r2.json()["items"][0]["unit_price"]) == price1


# === STATUS ===


def test_status_forward(client, auth_headers, customer_id, product_ids):
    (p1, _), _ = product_ids
    oid = client.post(
        "/api/v1/orders",
        json={"customer_id": customer_id, "items": [{"product_id": p1, "quantity": 1}]},
        headers=auth_headers,
    ).json()["id"]

    r = client.patch(
        f"/api/v1/orders/{oid}/status",
        json={"status": "preparing"},
        headers=auth_headers,
    )
    assert r.status_code == 200
    assert r.json()["status"] == "preparing"


def test_status_cancel_from_received(client, auth_headers, customer_id, product_ids):
    (p1, _), _ = product_ids
    oid = client.post(
        "/api/v1/orders",
        json={"customer_id": customer_id, "items": [{"product_id": p1, "quantity": 1}]},
        headers=auth_headers,
    ).json()["id"]

    r = client.patch(
        f"/api/v1/orders/{oid}/status",
        json={"status": "cancelled"},
        headers=auth_headers,
    )
    assert r.status_code == 200
    assert r.json()["status"] == "cancelled"


def test_status_cannot_reactivate_cancelled(
    client, auth_headers, customer_id, product_ids
):
    (p1, _), _ = product_ids
    oid = client.post(
        "/api/v1/orders",
        json={"customer_id": customer_id, "items": [{"product_id": p1, "quantity": 1}]},
        headers=auth_headers,
    ).json()["id"]

    client.patch(
        f"/api/v1/orders/{oid}/status",
        json={"status": "cancelled"},
        headers=auth_headers,
    )
    r = client.patch(
        f"/api/v1/orders/{oid}/status",
        json={"status": "preparing"},
        headers=auth_headers,
    )
    assert r.status_code == 422


def test_status_rejects_invalid_value(client, auth_headers, customer_id, product_ids):
    (p1, _), _ = product_ids
    oid = client.post(
        "/api/v1/orders",
        json={"customer_id": customer_id, "items": [{"product_id": p1, "quantity": 1}]},
        headers=auth_headers,
    ).json()["id"]

    r = client.patch(
        f"/api/v1/orders/{oid}/status",
        json={"status": "frozen"},
        headers=auth_headers,
    )
    assert r.status_code == 422


# === GET / LIST ===


def test_get_order_detail(client, auth_headers, customer_id, product_ids):
    (p1, _), _ = product_ids
    oid = client.post(
        "/api/v1/orders",
        json={"customer_id": customer_id, "items": [{"product_id": p1, "quantity": 4}]},
        headers=auth_headers,
    ).json()["id"]

    r = client.get(f"/api/v1/orders/{oid}", headers=auth_headers)
    assert r.status_code == 200
    assert len(r.json()["items"]) == 1


def test_list_orders_returns_compact_rows(
    client, auth_headers, customer_id, product_ids
):
    (p1, _), _ = product_ids
    client.post(
        "/api/v1/orders",
        json={"customer_id": customer_id, "items": [{"product_id": p1, "quantity": 1}]},
        headers=auth_headers,
    )
    r = client.get("/api/v1/orders", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["total"] >= 1
    row = body["items"][0]
    # Compact row has item_count, not items
    assert "item_count" in row
    assert "items" not in row


def test_list_orders_status_filter(client, auth_headers, customer_id, product_ids):
    (p1, _), _ = product_ids
    oid = client.post(
        "/api/v1/orders",
        json={"customer_id": customer_id, "items": [{"product_id": p1, "quantity": 1}]},
        headers=auth_headers,
    ).json()["id"]
    client.patch(
        f"/api/v1/orders/{oid}/status", json={"status": "ready"}, headers=auth_headers
    )

    r = client.get("/api/v1/orders?status=ready", headers=auth_headers)
    assert all(o["status"] == "ready" for o in r.json()["items"])

    r2 = client.get("/api/v1/orders?status=received", headers=auth_headers)
    assert all(o["status"] == "received" for o in r2.json()["items"])


def test_list_orders_customer_filter(client, auth_headers, customer_id, product_ids):
    (p1, _), _ = product_ids
    client.post(
        "/api/v1/orders",
        json={"customer_id": customer_id, "items": [{"product_id": p1, "quantity": 1}]},
        headers=auth_headers,
    )
    r = client.get(f"/api/v1/orders?customer_id={customer_id}", headers=auth_headers)
    assert all(o["customer"]["id"] == customer_id for o in r.json()["items"])


# === UPDATE ===


def test_update_order_replaces_items_and_total(
    client, auth_headers, customer_id, product_ids
):
    (p1, price1), (p2, price2) = product_ids
    oid = client.post(
        "/api/v1/orders",
        json={"customer_id": customer_id, "items": [{"product_id": p1, "quantity": 1}]},
        headers=auth_headers,
    ).json()["id"]

    r = client.put(
        f"/api/v1/orders/{oid}",
        json={"items": [{"product_id": p2, "quantity": 5}]},
        headers=auth_headers,
    )
    body = r.json()
    assert len(body["items"]) == 1
    assert body["items"][0]["product_id"] == p2
    assert float(body["total_amount"]) == price2 * 5


def test_update_order_notes_only(client, auth_headers, customer_id, product_ids):
    (p1, _), _ = product_ids
    oid = client.post(
        "/api/v1/orders",
        json={"customer_id": customer_id, "items": [{"product_id": p1, "quantity": 1}]},
        headers=auth_headers,
    ).json()["id"]

    r = client.put(
        f"/api/v1/orders/{oid}",
        json={"notes": "ring the bell"},
        headers=auth_headers,
    )
    assert r.json()["notes"] == "ring the bell"
    # Items untouched
    assert len(r.json()["items"]) == 1


# === PREFILL ===


def test_prefill_from_default_order(client, auth_headers, customer_id, product_ids):
    (p1, _), (p2, _) = product_ids
    # Give the customer a template
    client.put(
        f"/api/v1/customers/{customer_id}/default-order",
        json={
            "items": [
                {"product_id": p1, "quantity": 3},
                {"product_id": p2, "quantity": 2},
            ]
        },
        headers=auth_headers,
    )
    r = client.get(
        f"/api/v1/customers/{customer_id}/order-prefill", headers=auth_headers
    )
    assert r.status_code == 200
    body = r.json()
    assert len(body["items"]) == 2
    assert body["skipped_count"] == 0


def test_prefill_skips_inactive_products(
    client, auth_headers, customer_id, product_ids
):
    (p1, _), (p2, _) = product_ids
    client.put(
        f"/api/v1/customers/{customer_id}/default-order",
        json={
            "items": [
                {"product_id": p1, "quantity": 3},
                {"product_id": p2, "quantity": 2},
            ]
        },
        headers=auth_headers,
    )
    # Deactivate p2
    client.delete(f"/api/v1/products/{p2}", headers=auth_headers)

    r = client.get(
        f"/api/v1/customers/{customer_id}/order-prefill", headers=auth_headers
    )
    body = r.json()
    assert len(body["items"]) == 1
    assert body["items"][0]["product_id"] == p1
    assert body["skipped_count"] == 1


# === AUTH ===


def test_create_order_requires_auth(client, customer_id, product_ids):
    (p1, _), _ = product_ids
    r = client.post(
        "/api/v1/orders",
        json={"customer_id": customer_id, "items": [{"product_id": p1, "quantity": 1}]},
    )
    assert r.status_code == 401
