"""Category endpoint tests — Medium rigor.

Coverage:
  Create (3 tests):  success, duplicate name 409, auth required
  List   (3 tests):  empty, paginated, status filter
  Get    (2 tests):  existing, 404
  Update (2 tests):  partial update, rename collision 409
  Delete (3 tests):  soft-delete, hard-delete blocked when in use, hard-delete success
  Validation (2 tests):  name normalisation, empty name rejected

Total: 15 tests.
"""

import pytest

CATEGORY_PAYLOAD = {
    "name": "savoury",
    "display_order": 10,
}


# === CREATE ===


def test_create_category_returns_201(client, auth_headers):
    r = client.post("/api/v1/categories", json=CATEGORY_PAYLOAD, headers=auth_headers)
    assert r.status_code == 201
    body = r.json()
    assert body["name"] == "savoury"
    assert body["display_order"] == 10
    assert body["is_active"] is True
    assert "id" in body


def test_create_category_rejects_duplicate_name(client, auth_headers):
    client.post("/api/v1/categories", json=CATEGORY_PAYLOAD, headers=auth_headers)
    r = client.post("/api/v1/categories", json=CATEGORY_PAYLOAD, headers=auth_headers)
    assert r.status_code == 409
    assert "already exists" in r.json()["detail"].lower()


def test_create_category_requires_auth(client):
    r = client.post("/api/v1/categories", json=CATEGORY_PAYLOAD)
    assert r.status_code == 401


# === VALIDATION ===


def test_create_category_normalises_name(client, auth_headers):
    """Mixed case + whitespace should normalise to lowercase trimmed."""
    payload = {**CATEGORY_PAYLOAD, "name": "  Savoury  "}
    r = client.post("/api/v1/categories", json=payload, headers=auth_headers)
    assert r.status_code == 201
    assert r.json()["name"] == "savoury"


def test_create_category_rejects_empty_name(client, auth_headers):
    """Whitespace-only name normalises to empty, fails min_length=1."""
    payload = {**CATEGORY_PAYLOAD, "name": "   "}
    r = client.post("/api/v1/categories", json=payload, headers=auth_headers)
    assert r.status_code == 422


# === LIST ===


def test_list_categories_empty(client, auth_headers):
    r = client.get("/api/v1/categories", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["items"] == []
    assert body["total"] == 0


def test_list_categories_returns_paginated_results(client, auth_headers):
    for name in ["savoury", "sweet", "cake"]:
        client.post(
            "/api/v1/categories",
            json={"name": name, "display_order": 0},
            headers=auth_headers,
        )

    r = client.get("/api/v1/categories", headers=auth_headers)
    body = r.json()
    assert body["total"] == 3
    assert len(body["items"]) == 3


def test_list_categories_status_filter(client, auth_headers):
    """Active by default; status=inactive returns only deactivated."""
    create = client.post(
        "/api/v1/categories",
        json={"name": "active_cat", "display_order": 0},
        headers=auth_headers,
    )
    deactivated = client.post(
        "/api/v1/categories",
        json={"name": "inactive_cat", "display_order": 0},
        headers=auth_headers,
    )
    client.delete(
        f"/api/v1/categories/{deactivated.json()['id']}", headers=auth_headers
    )

    # Default (active)
    r = client.get("/api/v1/categories", headers=auth_headers)
    assert r.json()["total"] == 1

    # Inactive only
    r = client.get("/api/v1/categories?status=inactive", headers=auth_headers)
    assert r.json()["total"] == 1
    assert r.json()["items"][0]["name"] == "inactive_cat"

    # All
    r = client.get("/api/v1/categories?status=all", headers=auth_headers)
    assert r.json()["total"] == 2


# === GET ===


def test_get_category_returns_existing(client, auth_headers):
    create = client.post(
        "/api/v1/categories", json=CATEGORY_PAYLOAD, headers=auth_headers
    )
    category_id = create.json()["id"]

    r = client.get(f"/api/v1/categories/{category_id}", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["name"] == "savoury"


def test_get_category_returns_404_for_nonexistent(client, auth_headers):
    fake_id = "00000000-0000-0000-0000-000000000000"
    r = client.get(f"/api/v1/categories/{fake_id}", headers=auth_headers)
    assert r.status_code == 404


# === UPDATE ===


def test_update_category_partial(client, auth_headers):
    create = client.post(
        "/api/v1/categories", json=CATEGORY_PAYLOAD, headers=auth_headers
    )
    category_id = create.json()["id"]

    r = client.put(
        f"/api/v1/categories/{category_id}",
        json={"display_order": 99},
        headers=auth_headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["display_order"] == 99
    assert body["name"] == "savoury"  # unchanged


def test_update_category_rejects_rename_collision(client, auth_headers):
    """Renaming to an existing name should return 409."""
    a = client.post(
        "/api/v1/categories",
        json={"name": "savoury", "display_order": 0},
        headers=auth_headers,
    )
    b = client.post(
        "/api/v1/categories",
        json={"name": "sweet", "display_order": 0},
        headers=auth_headers,
    )
    b_id = b.json()["id"]

    r = client.put(
        f"/api/v1/categories/{b_id}",
        json={"name": "savoury"},
        headers=auth_headers,
    )
    assert r.status_code == 409


# === DELETE ===


def test_deactivate_category_sets_is_active_false(client, auth_headers):
    create = client.post(
        "/api/v1/categories", json=CATEGORY_PAYLOAD, headers=auth_headers
    )
    category_id = create.json()["id"]

    r = client.delete(f"/api/v1/categories/{category_id}", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["is_active"] is False


def test_hard_delete_blocked_when_products_reference_category(client, auth_headers):
    """Hard-delete returns 409 if any product still uses the category."""
    cat = client.post("/api/v1/categories", json=CATEGORY_PAYLOAD, headers=auth_headers)
    cat_id = cat.json()["id"]

    # Create a product using this category
    client.post(
        "/api/v1/products",
        json={
            "name": "Test Product",
            "category_id": cat_id,
            "unit_price": 20.00,
            "unit_label": "piece",
        },
        headers=auth_headers,
    )

    r = client.delete(f"/api/v1/categories/{cat_id}/hard", headers=auth_headers)
    assert r.status_code == 409
    assert "in use" in r.json()["detail"].lower()


def test_hard_delete_succeeds_when_no_products_reference(client, auth_headers):
    """Hard-delete works when category has no products."""
    cat = client.post("/api/v1/categories", json=CATEGORY_PAYLOAD, headers=auth_headers)
    cat_id = cat.json()["id"]

    r = client.delete(f"/api/v1/categories/{cat_id}/hard", headers=auth_headers)
    assert r.status_code == 204

    # Verify it's actually gone
    r = client.get(f"/api/v1/categories/{cat_id}", headers=auth_headers)
    assert r.status_code == 404
