"""Pytest fixtures using a real Postgres test database."""

import pytest
from app.core.config import settings
from app.core.database import get_db
from app.core.security import create_access_token, get_password_hash
from app.main import app
from app.models import Base, User
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# One engine for the whole test session. We create the schema once,
# then truncate tables between tests to keep them fast and isolated.
test_engine = create_engine(settings.TEST_DATABASE_URL, pool_pre_ping=True)
TestSessionLocal = sessionmaker(bind=test_engine, autocommit=False, autoflush=False)


@pytest.fixture(scope="session", autouse=True)
def setup_test_database():
    """Create all tables once at the start of the test session.

    Why drop_all then create_all rather than running migrations:
    Alembic migrations are designed for production deployments and would
    add overhead. Tests just need the latest schema, not the migration
    path. The cost is that test DB schema can drift from migration output
    if a developer forgets to autogenerate a migration — but pytest fails
    fast in that case because column references break.
    """
    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture(scope="function")
def db_session():
    """Fresh session per test, with all tables truncated to start clean.

    Faster than drop+create per test (~10x), still gives perfect isolation.
    """
    # Truncate all tables before each test. CASCADE handles FKs.
    with test_engine.connect() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())
        conn.commit()

    session = TestSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(scope="function")
def client(db_session):
    """FastAPI test client with the test database wired in."""

    def _get_db_override():
        yield db_session

    app.dependency_overrides[get_db] = _get_db_override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture(scope="function")
def test_user(db_session):
    """A persisted user for endpoints requiring authentication."""
    user = User(
        email="test@bakeriq.com",
        full_name="Test User",
        password_hash=get_password_hash("test-password-1234"),
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture(scope="function")
def auth_headers(test_user):
    """Authorization header fixture — most customer tests need this."""
    token = create_access_token(subject=test_user.id)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="function", autouse=True)
def mute_outbound_notifications(monkeypatch):
    """Prevent tests from firing real WhatsApp messages.

    Two triggers so far: submitting the registration form notifies the
    owner, and approving one notifies the customer. Both call Twilio
    directly, so without this a full suite run burns sandbox quota and
    spams two real phones.

    Patched at the module attribute rather than the import site, because
    the callers resolve the function at call time.
    """
    from app.services import (
        customer_notification_service,
        owner_notification_service,
    )

    monkeypatch.setattr(
        owner_notification_service,
        "notify_new_registration",
        lambda db, *, name, phone: None,
    )
    monkeypatch.setattr(
        customer_notification_service,
        "notify_approved",
        lambda db, customer: None,
    )
