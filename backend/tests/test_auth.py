"""End-to-end auth tests."""

USER_PAYLOAD = {
    "email": "alice@bakeriq.com",
    "full_name": "Alice",
    "password": "test-password-1234",
}


def test_register_creates_user(client):
    r = client.post("/api/v1/auth/register", json=USER_PAYLOAD)
    assert r.status_code == 201
    body = r.json()
    assert body["email"] == USER_PAYLOAD["email"]
    assert "password" not in body and "password_hash" not in body
    assert body["is_active"] is True


def test_register_rejects_duplicate_email(client):
    client.post("/api/v1/auth/register", json=USER_PAYLOAD)
    r = client.post("/api/v1/auth/register", json=USER_PAYLOAD)
    assert r.status_code == 409


def test_login_returns_token(client):
    client.post("/api/v1/auth/register", json=USER_PAYLOAD)
    r = client.post(
        "/api/v1/auth/login",
        data={"username": USER_PAYLOAD["email"], "password": USER_PAYLOAD["password"]},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["token_type"] == "bearer"
    assert len(body["access_token"]) > 50


def test_login_rejects_wrong_password(client):
    client.post("/api/v1/auth/register", json=USER_PAYLOAD)
    r = client.post(
        "/api/v1/auth/login",
        data={"username": USER_PAYLOAD["email"], "password": "wrong"},
    )
    assert r.status_code == 401


def test_me_requires_token(client):
    r = client.get("/api/v1/auth/me")
    assert r.status_code == 401


def test_me_with_valid_token(client):
    client.post("/api/v1/auth/register", json=USER_PAYLOAD)
    login = client.post(
        "/api/v1/auth/login",
        data={"username": USER_PAYLOAD["email"], "password": USER_PAYLOAD["password"]},
    )
    token = login.json()["access_token"]
    r = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["email"] == USER_PAYLOAD["email"]
