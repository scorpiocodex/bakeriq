"""web_link_service — the URLs the bot puts in WhatsApp messages."""

import pytest
from app.core.config import Settings, settings
from app.models.customer import Customer
from app.services import web_link_service


@pytest.fixture
def customer(db_session):
    c = Customer(
        name="Link Tester",
        primary_phone="+919888555002",
        whatsapp_enabled=True,
        is_active=True,
        address_line_1="1 Link Road",
        city="Kochi",
        state="Kerala",
        pincode="682020",
    )
    db_session.add(c)
    db_session.commit()
    db_session.refresh(c)
    return c


def test_default_base_url_includes_the_web_prefix():
    """The customer app is served under /web/. A default without it produced
    links that 404 even though the app itself was running."""
    default = Settings.model_fields["CUSTOMER_WEB_BASE_URL"].default
    assert default.rstrip("/").endswith("/web")


def test_link_is_base_plus_kind_plus_token(db_session, customer, monkeypatch):
    monkeypatch.setattr(settings, "CUSTOMER_WEB_BASE_URL", "https://example.test/web/")
    link, token = web_link_service.issue_link(db_session, customer=customer, kind="new")
    # A trailing slash on the base must not double up.
    assert link == f"https://example.test/web/new/{token}"
