"""Customer endpoint tests — Medium rigor."""

import pytest

CUSTOMER_PAYLOAD = {
    "name": "Anita Menon",
    "primary_phone": "+919999912345",
    "secondary_phone": "+919999900001",
    "preferred_channel_phone": "primary",
    "whatsapp_enabled": True,
    "address": "Pattom",
    "notes": "Daily customer",
}


# === CREATE ===


def test_create_customer_returns_201(client, auth_headers):
    r = client.post("/api/v1/customers", json=CUSTOMER_PAYLOAD, headers=auth_headers)
    assert r.status_code == 201
    body = r.json()
    assert body["name"] == "Anita Menon"
    assert body["primary_phone"] == "+919999912345"
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
    create = client.post(
        "/api/v1/customers", json=CUSTOMER_PAYLOAD, headers=auth_headers
    )
    customer_id = create.json()["id"]
    client.delete(f"/api/v1/customers/{customer_id}", headers=auth_headers)

    r = client.get("/api/v1/customers", headers=auth_headers)
    assert r.json()["total"] == 0

    r = client.get("/api/v1/customers?include_inactive=true", headers=auth_headers)
    assert r.json()["total"] == 1


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
