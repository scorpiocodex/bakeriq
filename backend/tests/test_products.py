"""Product endpoint tests — Medium rigor.

Coverage:
  Create (5 tests):  success, embedded category in response, bad category 422,
                     inactive category 422, auth required
  Validation (3 tests):  unit_price > 0, alias normalisation, name required
  List (4 tests):  empty, paginated, category filter, status filter
  Get (2 tests):  existing with embedded category, 404
  Update (2 tests):  partial update, change category
  Delete (1 test):  soft-delete sets is_active=false

Total: 17 tests.

Note: pytest fixtures from conftest.py provide `client` and `auth_headers`.
This file adds a `category_id` fixture that creates one category per test
run, so most product tests don't have to set up a category themselves.
"""

import pytest


@pytest.fixture
def category_id(client, auth_headers):
    """Creates a fresh 'sweet' category for each test that asks for it.

    Function-scoped (the default) — each test gets a fresh category in a
    fresh database, since the conftest pattern recreates the test DB
    between tests.
    """
    r = client.post(
        "/api/v1/categories",
        json={"name": "sweet", "display_order": 0},
        headers=auth_headers,
    )
    return r.json()["id"]


def make_product_payload(category_id: str, **overrides) -> dict:
    """Build a valid product payload. Override any field via kwargs.

    Centralises the 'minimal valid product' definition so each test
    only specifies what's interesting for that test.
    """
    base = {
        "name": "Veg Puff",
        "category_id": category_id,
        "unit_price": 20.00,
        "unit_label": "piece",
        "is_available_today": True,
        "aliases": ["puff", "veg puff"],
        "description": "Crispy savoury pastry",
    }
    base.update(overrides)
    return base


# === CREATE ===


def test_create_product_returns_201(client, auth_headers, category_id):
    payload = make_product_payload(category_id)
    r = client.post("/api/v1/products", json=payload, headers=auth_headers)
    assert r.status_code == 201
    body = r.json()
    assert body["name"] == "Veg Puff"
    # unit_price comes back as string (Decimal serialisation default)
    assert float(body["unit_price"]) == 20.00
    assert body["is_active"] is True
    assert "id" in body


def test_create_product_response_embeds_full_category(
    client, auth_headers, category_id
):
    """Response contains the full category object, not just the id."""
    payload = make_product_payload(category_id)
    r = client.post("/api/v1/products", json=payload, headers=auth_headers)
    body = r.json()

    assert "category" in body
    assert body["category"]["id"] == category_id
    assert body["category"]["name"] == "sweet"
    assert "display_order" in body["category"]


def test_create_product_rejects_nonexistent_category(client, auth_headers):
    """422 (not 404) — the bad data is in the request body."""
    fake_category = "00000000-0000-0000-0000-000000000000"
    payload = make_product_payload(fake_category)
    r = client.post("/api/v1/products", json=payload, headers=auth_headers)
    assert r.status_code == 422
    assert "does not exist" in r.json()["detail"].lower()


def test_create_product_rejects_inactive_category(client, auth_headers, category_id):
    """Owner can't add a product to a deactivated category."""
    # Deactivate the category
    client.delete(f"/api/v1/categories/{category_id}", headers=auth_headers)

    payload = make_product_payload(category_id)
    r = client.post("/api/v1/products", json=payload, headers=auth_headers)
    assert r.status_code == 422
    assert "inactive" in r.json()["detail"].lower()


def test_create_product_requires_auth(client, category_id):
    """No auth header → 401."""
    payload = make_product_payload(category_id)
    r = client.post("/api/v1/products", json=payload)
    assert r.status_code == 401


# === VALIDATION ===


def test_create_product_rejects_zero_or_negative_price(
    client, auth_headers, category_id
):
    """unit_price has gt=0 constraint."""
    for bad_price in [0, -1, -50.00]:
        payload = make_product_payload(category_id, unit_price=bad_price)
        r = client.post("/api/v1/products", json=payload, headers=auth_headers)
        assert (
            r.status_code == 422
        ), f"Expected 422 for price {bad_price}, got {r.status_code}"


def test_create_product_normalises_aliases(client, auth_headers, category_id):
    """Mixed case + duplicates + whitespace should normalise."""
    payload = make_product_payload(
        category_id,
        aliases=["Puff", "PUFF ", "puff", "  ", "Veg Puff"],
    )
    r = client.post("/api/v1/products", json=payload, headers=auth_headers)
    assert r.status_code == 201
    aliases = r.json()["aliases"]
    # Should be ["puff", "veg puff"] — duplicates dropped, lowercase, trimmed
    assert "puff" in aliases
    assert "veg puff" in aliases
    assert len(aliases) == 2


def test_create_product_requires_name(client, auth_headers, category_id):
    """Empty name → 422."""
    payload = make_product_payload(category_id, name="")
    r = client.post("/api/v1/products", json=payload, headers=auth_headers)
    assert r.status_code == 422


# === LIST ===


def test_list_products_empty(client, auth_headers):
    r = client.get("/api/v1/products", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["items"] == []
    assert body["total"] == 0


def test_list_products_returns_paginated_results(client, auth_headers, category_id):
    for i in range(3):
        payload = make_product_payload(category_id, name=f"Product {i}")
        client.post("/api/v1/products", json=payload, headers=auth_headers)

    r = client.get("/api/v1/products", headers=auth_headers)
    body = r.json()
    assert body["total"] == 3
    assert len(body["items"]) == 3
    # Each product's response should have embedded category
    for item in body["items"]:
        assert item["category"]["id"] == category_id


def test_list_products_filter_by_category(client, auth_headers, category_id):
    """Multiple categories, filter to one."""
    # Create a second category
    other_cat = client.post(
        "/api/v1/categories",
        json={"name": "savoury", "display_order": 0},
        headers=auth_headers,
    )
    other_cat_id = other_cat.json()["id"]

    # 2 products in 'sweet', 1 in 'savoury'
    for name in ["Ladoo", "Jilebi"]:
        client.post(
            "/api/v1/products",
            json=make_product_payload(category_id, name=name),
            headers=auth_headers,
        )
    client.post(
        "/api/v1/products",
        json=make_product_payload(other_cat_id, name="Veg Puff"),
        headers=auth_headers,
    )

    # Filter by 'sweet' category
    r = client.get(
        f"/api/v1/products?category_id={category_id}",
        headers=auth_headers,
    )
    assert r.json()["total"] == 2

    # Filter by 'savoury' category
    r = client.get(
        f"/api/v1/products?category_id={other_cat_id}",
        headers=auth_headers,
    )
    assert r.json()["total"] == 1
    assert r.json()["items"][0]["name"] == "Veg Puff"


def test_list_products_status_filter(client, auth_headers, category_id):
    """Active by default; deactivated products show only with status filter."""
    create = client.post(
        "/api/v1/products",
        json=make_product_payload(category_id),
        headers=auth_headers,
    )
    product_id = create.json()["id"]
    client.delete(f"/api/v1/products/{product_id}", headers=auth_headers)

    # Default (active) — should be empty
    r = client.get("/api/v1/products", headers=auth_headers)
    assert r.json()["total"] == 0

    # Inactive only
    r = client.get("/api/v1/products?status=inactive", headers=auth_headers)
    assert r.json()["total"] == 1


# === GET ===


def test_get_product_returns_existing_with_category(client, auth_headers, category_id):
    create = client.post(
        "/api/v1/products",
        json=make_product_payload(category_id),
        headers=auth_headers,
    )
    product_id = create.json()["id"]

    r = client.get(f"/api/v1/products/{product_id}", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "Veg Puff"
    # Embedded category should still be present
    assert body["category"]["id"] == category_id


def test_get_product_returns_404_for_nonexistent(client, auth_headers):
    fake_id = "00000000-0000-0000-0000-000000000000"
    r = client.get(f"/api/v1/products/{fake_id}", headers=auth_headers)
    assert r.status_code == 404


# === UPDATE ===


def test_update_product_partial(client, auth_headers, category_id):
    create = client.post(
        "/api/v1/products",
        json=make_product_payload(category_id),
        headers=auth_headers,
    )
    product_id = create.json()["id"]

    r = client.put(
        f"/api/v1/products/{product_id}",
        json={"unit_price": 25.00, "is_available_today": False},
        headers=auth_headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert float(body["unit_price"]) == 25.00
    assert body["is_available_today"] is False
    # Unchanged fields preserved
    assert body["name"] == "Veg Puff"


def test_update_product_change_category(client, auth_headers, category_id):
    """Move a product to a different category."""
    other_cat = client.post(
        "/api/v1/categories",
        json={"name": "savoury", "display_order": 0},
        headers=auth_headers,
    )
    other_cat_id = other_cat.json()["id"]

    create = client.post(
        "/api/v1/products",
        json=make_product_payload(category_id),
        headers=auth_headers,
    )
    product_id = create.json()["id"]

    r = client.put(
        f"/api/v1/products/{product_id}",
        json={"category_id": other_cat_id},
        headers=auth_headers,
    )
    assert r.status_code == 200
    assert r.json()["category"]["id"] == other_cat_id
    assert r.json()["category"]["name"] == "savoury"


# === DELETE (soft) ===


def test_deactivate_product_sets_is_active_false(client, auth_headers, category_id):
    create = client.post(
        "/api/v1/products",
        json=make_product_payload(category_id),
        headers=auth_headers,
    )
    product_id = create.json()["id"]

    r = client.delete(f"/api/v1/products/{product_id}", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["is_active"] is False
