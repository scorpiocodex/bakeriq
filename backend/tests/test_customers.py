"""Customer endpoint tests — Medium rigor.

Coverage:
  Create (6 tests): success, phone normalisation, bad phone, duplicate
    phone, cross-column phone uniqueness, auth required
  Pincode (2 tests): bad PIN format rejected, PIN whitespace normalised
  List (4 tests): empty, paginated, inactive filtering, search by name
  Get (2 tests): existing, 404
  Update (2 tests): partial update, phone collision rejected
  Delete (1 test): soft delete sets is_active=false

Total: 17 tests.
"""

import pytest

# Default payload used across most tests. Includes all required fields
# (name, primary_phone, address_line_1, city, state, pincode) plus a few
# optional ones (secondary_phone, address_line_2, whatsapp_enabled).
# Test placeholder per the agreed convention — not a real address.
CUSTOMER_PAYLOAD = {
    "name": "Anita Menon",
    "primary_phone": "+919999912345",
    "secondary_phone": "+919999900001",
    "preferred_channel_phone": "primary",
    "whatsapp_enabled": True,
    "address_line_1": "Test Bakery",
    "address_line_2": "Test Street",
    "city": "Kochi",
    "state": "Kerala",
    "pincode": "682001",
    "notes": "Daily customer",
}


# === CREATE ===


def test_create_customer_returns_201(client, auth_headers):
    r = client.post("/api/v1/customers", json=CUSTOMER_PAYLOAD, headers=auth_headers)
    assert r.status_code == 201
    body = r.json()
    assert body["name"] == "Anita Menon"
    assert body["primary_phone"] == "+919999912345"
    assert body["address_line_1"] == "Test Bakery"
    assert body["city"] == "Kochi"
    assert body["state"] == "Kerala"
    assert body["pincode"] == "682001"
    assert body["is_active"] is True
    assert "id" in body


def test_create_customer_normalises_phone_whitespace(client, auth_headers):
    payload = {**CUSTOMER_PAYLOAD, "primary_phone": "+91 99999 12345"}
    r = client.post("/api/v1/customers", json=payload, headers=auth_headers)
    assert r.status_code == 201
    assert r.json()["primary_phone"] == "+919999912345"


def test_create_customer_rejects_bad_phone_format(client, auth_headers):
    payload = {**CUSTOMER_PAYLOAD, "primary_phone": "not-a-phone"}
    r = client.post("/api/v1/customers", json=payload, headers=auth_headers)
    assert r.status_code == 422


def test_create_customer_rejects_duplicate_primary_phone(client, auth_headers):
    client.post("/api/v1/customers", json=CUSTOMER_PAYLOAD, headers=auth_headers)
    duplicate = {**CUSTOMER_PAYLOAD, "name": "Different Name"}
    r = client.post("/api/v1/customers", json=duplicate, headers=auth_headers)
    assert r.status_code == 409
    assert "+919999912345" in r.json()["detail"]


def test_create_customer_rejects_phone_used_as_anothers_secondary(client, auth_headers):
    """Cross-column uniqueness — primary can't match someone else's secondary."""
    client.post("/api/v1/customers", json=CUSTOMER_PAYLOAD, headers=auth_headers)
    second = {
        **CUSTOMER_PAYLOAD,
        "name": "Other Customer",
        "primary_phone": "+919999900001",  # was first customer's secondary
        "secondary_phone": None,
    }
    r = client.post("/api/v1/customers", json=second, headers=auth_headers)
    assert r.status_code == 409


def test_create_customer_requires_auth(client):
    r = client.post("/api/v1/customers", json=CUSTOMER_PAYLOAD)
    assert r.status_code == 401


# === PINCODE VALIDATION ===


def test_create_customer_rejects_bad_pincode(client, auth_headers):
    """5 digits, 7 digits, alphabetic — all should fail the ^\\d{6}$ regex."""
    for bad_pin in ["12345", "1234567", "abc123", "68200a"]:
        payload = {**CUSTOMER_PAYLOAD, "pincode": bad_pin}
        r = client.post("/api/v1/customers", json=payload, headers=auth_headers)
        assert (
            r.status_code == 422
        ), f"Expected 422 for pincode '{bad_pin}', got {r.status_code}"


def test_create_customer_normalises_pincode_whitespace(client, auth_headers):
    """User pastes '682 314' from somewhere — backend strips space, accepts it."""
    payload = {**CUSTOMER_PAYLOAD, "pincode": "682 314"}
    r = client.post("/api/v1/customers", json=payload, headers=auth_headers)
    assert r.status_code == 201
    assert r.json()["pincode"] == "682314"


# === LIST ===


def test_list_customers_empty(client, auth_headers):
    r = client.get("/api/v1/customers", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["items"] == []
    assert body["total"] == 0


def test_list_customers_returns_paginated_results(client, auth_headers):
    for i in range(3):
        payload = {
            **CUSTOMER_PAYLOAD,
            "name": f"Customer {i}",
            "primary_phone": f"+91999991234{i}",
            "secondary_phone": None,
        }
        client.post("/api/v1/customers", json=payload, headers=auth_headers)

    r = client.get("/api/v1/customers", headers=auth_headers)
    body = r.json()
    assert body["total"] == 3
    assert len(body["items"]) == 3


def test_list_customers_filters_inactive_by_default(client, auth_headers):
    """Default behaviour: deactivated customers don't show up."""
    create = client.post(
        "/api/v1/customers", json=CUSTOMER_PAYLOAD, headers=auth_headers
    )
    customer_id = create.json()["id"]
    client.delete(f"/api/v1/customers/{customer_id}", headers=auth_headers)

    # No status param — default is 'active'
    r = client.get("/api/v1/customers", headers=auth_headers)
    assert r.json()["total"] == 0


def test_list_customers_status_inactive_returns_only_inactive(client, auth_headers):
    """status=inactive returns ONLY deactivated customers."""
    # Create an active customer
    active = client.post(
        "/api/v1/customers",
        json={
            **CUSTOMER_PAYLOAD,
            "name": "Active One",
            "primary_phone": "+919999911111",
            "secondary_phone": None,
        },
        headers=auth_headers,
    )
    # Create another and deactivate it
    inactive = client.post(
        "/api/v1/customers",
        json={
            **CUSTOMER_PAYLOAD,
            "name": "Inactive One",
            "primary_phone": "+919999922222",
            "secondary_phone": None,
        },
        headers=auth_headers,
    )
    client.delete(f"/api/v1/customers/{inactive.json()['id']}", headers=auth_headers)

    r = client.get("/api/v1/customers?status=inactive", headers=auth_headers)
    body = r.json()
    assert body["total"] == 1
    assert body["items"][0]["name"] == "Inactive One"
    assert body["items"][0]["is_active"] is False


def test_list_customers_status_all_returns_both(client, auth_headers):
    """status=all returns active AND inactive customers."""
    active = client.post(
        "/api/v1/customers",
        json={
            **CUSTOMER_PAYLOAD,
            "name": "Active One",
            "primary_phone": "+919999911111",
            "secondary_phone": None,
        },
        headers=auth_headers,
    )
    inactive = client.post(
        "/api/v1/customers",
        json={
            **CUSTOMER_PAYLOAD,
            "name": "Inactive One",
            "primary_phone": "+919999922222",
            "secondary_phone": None,
        },
        headers=auth_headers,
    )
    client.delete(f"/api/v1/customers/{inactive.json()['id']}", headers=auth_headers)

    r = client.get("/api/v1/customers?status=all", headers=auth_headers)
    assert r.json()["total"] == 2


def test_list_customers_rejects_invalid_status(client, auth_headers):
    """status=foo returns 422 thanks to the Query pattern validation."""
    r = client.get("/api/v1/customers?status=foo", headers=auth_headers)
    assert r.status_code == 422


def test_list_customers_search_by_name(client, auth_headers):
    payloads = [
        {
            **CUSTOMER_PAYLOAD,
            "name": "Anita Menon",
            "primary_phone": "+919999912345",
            "secondary_phone": None,
        },
        {
            **CUSTOMER_PAYLOAD,
            "name": "Ravi Kumar",
            "primary_phone": "+919999923456",
            "secondary_phone": None,
        },
    ]
    for p in payloads:
        client.post("/api/v1/customers", json=p, headers=auth_headers)

    r = client.get("/api/v1/customers?search=anita", headers=auth_headers)
    body = r.json()
    assert body["total"] == 1
    assert body["items"][0]["name"] == "Anita Menon"


# === GET ===


def test_get_customer_returns_existing(client, auth_headers):
    create = client.post(
        "/api/v1/customers", json=CUSTOMER_PAYLOAD, headers=auth_headers
    )
    customer_id = create.json()["id"]

    r = client.get(f"/api/v1/customers/{customer_id}", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["name"] == "Anita Menon"


def test_get_customer_returns_404_for_nonexistent(client, auth_headers):
    fake_id = "00000000-0000-0000-0000-000000000000"
    r = client.get(f"/api/v1/customers/{fake_id}", headers=auth_headers)
    assert r.status_code == 404


# === UPDATE ===


def test_update_customer_partial(client, auth_headers):
    create = client.post(
        "/api/v1/customers", json=CUSTOMER_PAYLOAD, headers=auth_headers
    )
    customer_id = create.json()["id"]

    r = client.put(
        f"/api/v1/customers/{customer_id}",
        json={"notes": "Updated notes"},
        headers=auth_headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["notes"] == "Updated notes"
    assert body["name"] == "Anita Menon"  # unchanged
    assert body["pincode"] == "682001"  # unchanged


def test_update_customer_rejects_phone_collision(client, auth_headers):
    a = client.post("/api/v1/customers", json=CUSTOMER_PAYLOAD, headers=auth_headers)
    other_payload = {
        **CUSTOMER_PAYLOAD,
        "name": "Other",
        "primary_phone": "+919999923456",
        "secondary_phone": None,
    }
    b = client.post("/api/v1/customers", json=other_payload, headers=auth_headers)
    b_id = b.json()["id"]

    r = client.put(
        f"/api/v1/customers/{b_id}",
        json={"primary_phone": "+919999912345"},  # belongs to A
        headers=auth_headers,
    )
    assert r.status_code == 409


# === DELETE (soft) ===


def test_deactivate_customer_sets_is_active_false(client, auth_headers):
    create = client.post(
        "/api/v1/customers", json=CUSTOMER_PAYLOAD, headers=auth_headers
    )
    customer_id = create.json()["id"]

    r = client.delete(f"/api/v1/customers/{customer_id}", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["is_active"] is False
