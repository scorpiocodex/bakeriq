"""The first-account script (scripts/create_owner.py)."""

import pytest
from app.core.security import verify_password
from pydantic import ValidationError
from scripts.create_owner import OwnerExistsError, create_owner


def test_creates_an_active_superuser(db_session):
    user = create_owner(
        db_session,
        email="first@bakeriq.com",
        full_name="First Owner",
        password="a-good-password",
    )
    assert user.is_superuser is True
    assert user.is_active is True
    assert user.password_hash != "a-good-password"
    assert verify_password("a-good-password", user.password_hash)


def test_created_owner_can_register_further_accounts(client, db_session):
    create_owner(
        db_session,
        email="first@bakeriq.com",
        full_name=None,
        password="a-good-password",
    )
    token = client.post(
        "/api/v1/auth/login",
        data={"username": "first@bakeriq.com", "password": "a-good-password"},
    ).json()["access_token"]
    r = client.post(
        "/api/v1/auth/register",
        json={
            "email": "staff@bakeriq.com",
            "full_name": "Staff",
            "password": "another-password",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 201


def test_refuses_an_existing_email(db_session):
    create_owner(
        db_session,
        email="first@bakeriq.com",
        full_name=None,
        password="a-good-password",
    )
    with pytest.raises(OwnerExistsError):
        create_owner(
            db_session,
            email="first@bakeriq.com",
            full_name=None,
            password="different-password",
        )


def test_applies_the_same_password_rules_as_the_api(db_session):
    with pytest.raises(ValidationError):
        create_owner(
            db_session, email="first@bakeriq.com", full_name=None, password="short"
        )
