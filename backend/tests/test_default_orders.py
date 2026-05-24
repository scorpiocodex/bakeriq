"""Default Order endpoint tests — Medium rigor.

Coverage:
  Upsert create (4): success, embedded products, bad product 422,
                     inactive product 422
  Upsert replace (2): replacing items wholesale, updating notes/is_active
  Get (3): existing, no-template 404, nonexistent-customer 404
  Delete (2): success + cascade, no-template 404
  Validation (2): quantity > 0, auth required

Total: 13 tests.
"""

import pytest

# Fixtures: create a customer and two products to build templates from.
# Both function-scoped (fresh per test, fresh DB per test via conftest).


@pytest.fixture
def customer_id(client, auth_headers):
    r = client.post(
        "/api/v1/customers",
        json={
            "name": "Template Customer",
            "primary_phone": "+919999900001",
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
        json={"name": "sweet", "display_order": 0},
        headers=auth_headers,
    )
    return r.json()["id"]


@pytest.fixture
def product_ids(client, auth_headers, category_id):
    """Two products to put in templates. Returns (id1, id2)."""
    ids = []
    for name, price in [("Ladoo", 15.00), ("Jilebi", 12.00)]:
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
        ids.append(r.json()["id"])
    return tuple(ids)


def url(customer_id):
    return f"/api/v1/customers/{customer_id}/default-order"


# === UPSERT — CREATE ===


def test_upsert_creates_template(client, auth_headers, customer_id, product_ids):
    p1, p2 = product_ids
    payload = {
        "notes": "usual morning order",
        "is_active": True,
        "items": [
            {"product_id": p1, "quantity": 5},
            {"product_id": p2, "quantity": 1},
        ],
    }
    r = client.put(url(customer_id), json=payload, headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["customer_id"] == customer_id
    assert body["notes"] == "usual morning order"
    assert body["is_active"] is True
    assert len(body["items"]) == 2


def test_upsert_response_embeds_products(
    client, auth_headers, customer_id, product_ids
):
    p1, p2 = product_ids
    payload = {
        "items": [{"product_id": p1, "quantity": 5}],
    }
    r = client.put(url(customer_id), json=payload, headers=auth_headers)
    body = r.json()
    item = body["items"][0]
    assert item["product_id"] == p1
    assert item["quantity"] == 5
    # Embedded product object
    assert item["product"]["id"] == p1
    assert item["product"]["name"] == "Ladoo"
    assert "category" in item["product"]


def test_upsert_rejects_nonexistent_product(client, auth_headers, customer_id):
    fake_product = "00000000-0000-0000-0000-000000000000"
    payload = {"items": [{"product_id": fake_product, "quantity": 1}]}
    r = client.put(url(customer_id), json=payload, headers=auth_headers)
    assert r.status_code == 422
    assert "does not exist" in r.json()["detail"].lower()


def test_upsert_rejects_inactive_product(
    client, auth_headers, customer_id, product_ids
):
    p1, _ = product_ids
    # Deactivate the product
    client.delete(f"/api/v1/products/{p1}", headers=auth_headers)

    payload = {"items": [{"product_id": p1, "quantity": 1}]}
    r = client.put(url(customer_id), json=payload, headers=auth_headers)
    assert r.status_code == 422
    assert "inactive" in r.json()["detail"].lower()


# === UPSERT — REPLACE ===


def test_upsert_replaces_items_wholesale(
    client, auth_headers, customer_id, product_ids
):
    p1, p2 = product_ids
    # First template: both products
    client.put(
        url(customer_id),
        json={
            "items": [
                {"product_id": p1, "quantity": 5},
                {"product_id": p2, "quantity": 1},
            ]
        },
        headers=auth_headers,
    )
    # Replace with just p2, different quantity
    r = client.put(
        url(customer_id),
        json={"items": [{"product_id": p2, "quantity": 9}]},
        headers=auth_headers,
    )
    body = r.json()
    assert len(body["items"]) == 1
    assert body["items"][0]["product_id"] == p2
    assert body["items"][0]["quantity"] == 9


def test_upsert_updates_notes_and_active(
    client, auth_headers, customer_id, product_ids
):
    p1, _ = product_ids
    client.put(
        url(customer_id),
        json={
            "notes": "first",
            "is_active": True,
            "items": [{"product_id": p1, "quantity": 1}],
        },
        headers=auth_headers,
    )
    r = client.put(
        url(customer_id),
        json={
            "notes": "updated",
            "is_active": False,
            "items": [{"product_id": p1, "quantity": 1}],
        },
        headers=auth_headers,
    )
    body = r.json()
    assert body["notes"] == "updated"
    assert body["is_active"] is False


# === GET ===


def test_get_existing_template(client, auth_headers, customer_id, product_ids):
    p1, _ = product_ids
    client.put(
        url(customer_id),
        json={"items": [{"product_id": p1, "quantity": 3}]},
        headers=auth_headers,
    )
    r = client.get(url(customer_id), headers=auth_headers)
    assert r.status_code == 200
    assert len(r.json()["items"]) == 1


def test_get_no_template_returns_404(client, auth_headers, customer_id):
    """Customer exists but has no template yet."""
    r = client.get(url(customer_id), headers=auth_headers)
    assert r.status_code == 404
    assert "no default order" in r.json()["detail"].lower()


def test_get_nonexistent_customer_returns_404(client, auth_headers):
    fake_customer = "00000000-0000-0000-0000-000000000000"
    r = client.get(url(fake_customer), headers=auth_headers)
    assert r.status_code == 404
    assert "customer not found" in r.json()["detail"].lower()


# === DELETE ===


def test_delete_template_succeeds(client, auth_headers, customer_id, product_ids):
    p1, _ = product_ids
    client.put(
        url(customer_id),
        json={"items": [{"product_id": p1, "quantity": 1}]},
        headers=auth_headers,
    )
    r = client.delete(url(customer_id), headers=auth_headers)
    assert r.status_code == 204

    # Confirm it's gone
    r = client.get(url(customer_id), headers=auth_headers)
    assert r.status_code == 404


def test_delete_no_template_returns_404(client, auth_headers, customer_id):
    r = client.delete(url(customer_id), headers=auth_headers)
    assert r.status_code == 404


# === VALIDATION ===


def test_upsert_rejects_zero_quantity(client, auth_headers, customer_id, product_ids):
    p1, _ = product_ids
    payload = {"items": [{"product_id": p1, "quantity": 0}]}
    r = client.put(url(customer_id), json=payload, headers=auth_headers)
    assert r.status_code == 422


def test_upsert_requires_auth(client, customer_id, product_ids):
    p1, _ = product_ids
    payload = {"items": [{"product_id": p1, "quantity": 1}]}
    r = client.put(url(customer_id), json=payload)
    assert r.status_code == 401
