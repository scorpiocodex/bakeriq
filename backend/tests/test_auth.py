"""End-to-end auth tests."""

import pytest
from app.core.security import create_access_token, get_password_hash
from app.models import User

USER_PAYLOAD = {
    "email": "alice@bakeriq.com",
    "full_name": "Alice",
    "password": "test-password-1234",
}


@pytest.fixture
def superuser_headers(db_session):
    """Authorization header for a superuser — the only kind that may register accounts."""
    owner = User(
        email="owner-test@bakeriq.com",
        full_name="Owner",
        password_hash=get_password_hash("owner-password-1234"),
        is_superuser=True,
    )
    db_session.add(owner)
    db_session.commit()
    db_session.refresh(owner)
    return {"Authorization": f"Bearer {create_access_token(subject=owner.id)}"}


@pytest.fixture
def alice(db_session):
    """USER_PAYLOAD as a stored account, created directly so the login tests
    don't depend on the register endpoint."""
    user = User(
        email=USER_PAYLOAD["email"],
        full_name=USER_PAYLOAD["full_name"],
        password_hash=get_password_hash(USER_PAYLOAD["password"]),
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def _login(client, email, password):
    return client.post("/api/v1/auth/login", data={"username": email, "password": password})


# --- register: superuser only -------------------------------------------------


def test_register_requires_authentication(client):
    r = client.post("/api/v1/auth/register", json=USER_PAYLOAD)
    assert r.status_code == 401


def test_register_rejects_a_normal_user(client, auth_headers):
    r = client.post("/api/v1/auth/register", json=USER_PAYLOAD, headers=auth_headers)
    assert r.status_code == 403
    # And it must not have created the account.
    assert _login(client, USER_PAYLOAD["email"], USER_PAYLOAD["password"]).status_code == 401


def test_register_creates_user_for_a_superuser(client, superuser_headers):
    r = client.post("/api/v1/auth/register", json=USER_PAYLOAD, headers=superuser_headers)
    assert r.status_code == 201
    body = r.json()
    assert body["email"] == USER_PAYLOAD["email"]
    assert "password" not in body and "password_hash" not in body
    assert body["is_active"] is True
    # Accounts created through the API are never superusers.
    assert body["is_superuser"] is False


def test_registered_user_can_log_in(client, superuser_headers):
    client.post("/api/v1/auth/register", json=USER_PAYLOAD, headers=superuser_headers)
    r = _login(client, USER_PAYLOAD["email"], USER_PAYLOAD["password"])
    assert r.status_code == 200


def test_register_rejects_duplicate_email(client, superuser_headers):
    client.post("/api/v1/auth/register", json=USER_PAYLOAD, headers=superuser_headers)
    r = client.post("/api/v1/auth/register", json=USER_PAYLOAD, headers=superuser_headers)
    assert r.status_code == 409


# --- login / me ---------------------------------------------------------------


def test_login_returns_token(client, alice):
    r = _login(client, USER_PAYLOAD["email"], USER_PAYLOAD["password"])
    assert r.status_code == 200
    body = r.json()
    assert body["token_type"] == "bearer"
    assert len(body["access_token"]) > 50


def test_login_rejects_wrong_password(client, alice):
    r = _login(client, USER_PAYLOAD["email"], "wrong")
    assert r.status_code == 401


def test_me_requires_token(client):
    r = client.get("/api/v1/auth/me")
    assert r.status_code == 401


def test_me_with_valid_token(client, alice):
    token = _login(client, USER_PAYLOAD["email"], USER_PAYLOAD["password"]).json()["access_token"]
    r = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["email"] == USER_PAYLOAD["email"]
