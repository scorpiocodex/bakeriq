"""Tests for customer_handler — handle_customer_message dispatcher.

The dispatcher returns list[Reply] | None:
  - list[Reply] when a fast-path keyword or button label matched.
  - None when no match (caller routes to the LLM safety valve).

Most handlers return [text_reply, nav_reply]. Cart-link paths return a
single template reply. Greeting can be either a single template reply
(when CONTENT_SID_GREETING is set) or [text, nav_template] fallback.

These tests run against the real test Postgres. They do NOT hit Twilio
— handle_customer_message is pure, building Reply objects that the
webhook layer dispatches separately.
"""

from datetime import datetime, timedelta

import pytest
from app.core.config import settings
from app.models.category import Category
from app.models.customer import Customer
from app.models.order import Order, OrderStatus
from app.models.product import Product
from app.services.customer_handler import handle_customer_message
from app.services.reply import Reply

# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def customer(db_session):
    """A real customer in the DB with a unique phone."""
    c = Customer(
        name="Test Customer",
        primary_phone="+919888777222",
        whatsapp_enabled=True,
        is_active=True,
    )
    db_session.add(c)
    db_session.commit()
    db_session.refresh(c)
    return c


@pytest.fixture
def stub_products(db_session):
    """Two products in two categories for menu rendering tests.

    Two categories proves the grouping logic; two items per category
    would prove ordering but isn't necessary at this scope.
    """
    cat1 = Category(name="savoury", display_order=1, is_active=True)
    cat2 = Category(name="sweet", display_order=2, is_active=True)
    db_session.add_all([cat1, cat2])
    db_session.flush()

    p1 = Product(
        name="Test Puff",
        category_id=cat1.id,
        unit_price=10,
        unit_label="piece",
        is_available_today=True,
        is_active=True,
    )
    p2 = Product(
        name="Test Ladoo",
        category_id=cat2.id,
        unit_price=20,
        unit_label="piece",
        is_available_today=True,
        is_active=True,
    )
    db_session.add_all([p1, p2])
    db_session.commit()
    return [p1, p2]


@pytest.fixture
def customer_with_order(db_session, customer):
    """A customer who has a single non-draft, non-cancelled order.

    Used for order-status and reorder-last tests where the handler needs
    a real order row to read from.
    """
    order = Order(
        customer_id=customer.id,
        status=OrderStatus.received,
        is_draft=False,
        total_amount=50,
        created_at=datetime.utcnow() - timedelta(minutes=5),
    )
    db_session.add(order)
    db_session.commit()
    db_session.refresh(order)
    return customer, order


@pytest.fixture
def clear_content_sids(monkeypatch):
    """Force all CONTENT_SID_* to None so handlers exercise text fallbacks."""
    monkeypatch.setattr(settings, "CONTENT_SID_GREETING", None)
    monkeypatch.setattr(settings, "CONTENT_SID_NAV", None)
    monkeypatch.setattr(settings, "CONTENT_SID_CART_LINK", None)
    monkeypatch.setattr(settings, "CONTENT_SID_FALLBACK", None)


# ============================================================
# Helpers
# ============================================================


def assert_text_reply(reply: Reply, contains: str | None = None) -> None:
    """Assert a Reply is a text reply, optionally containing a substring."""
    assert reply.content_sid is None, (
        f"Expected text reply, got template (sid={reply.content_sid})"
    )
    assert reply.body is not None
    if contains is not None:
        assert contains in reply.body, (
            f"Expected {contains!r} in reply body, got: {reply.body!r}"
        )


def assert_template_reply(
    reply: Reply,
    expected_sid: str | None,
    expected_variables: dict | None = None,
) -> None:
    """Assert a Reply is a template reply with the expected SID and variables.

    `expected_sid` accepts Optional because callers pass settings.CONTENT_SID_*
    values that are typed as Optional[str]. We assert non-None at the top so
    the type narrows for downstream comparisons.
    """
    assert expected_sid is not None, (
        "Test invariant: expected_sid must be set on the settings object. "
        "Either run with .env CONTENT_SID_* populated, or write the test "
        "against the fallback branch."
    )
    assert reply.body is None, f"Expected template reply, got text: {reply.body!r}"
    assert reply.content_sid == expected_sid, (
        f"Expected SID {expected_sid}, got {reply.content_sid}"
    )
    if expected_variables is not None:
        assert reply.content_variables == expected_variables, (
            f"Expected variables {expected_variables}, got {reply.content_variables}"
        )


# ============================================================
# Greeting
# ============================================================


class TestGreeting:
    """The greeting path uses bakeriq_greeting if SID is set (single template
    reply, three buttons baked in), or [text, nav_template] fallback."""

    def test_returns_template_reply_with_first_name_when_sid_set(
        self, db_session, customer
    ):
        replies = handle_customer_message(db_session, customer, "hi")
        assert replies is not None
        assert len(replies) == 1
        assert_template_reply(
            replies[0],
            settings.CONTENT_SID_GREETING,
            expected_variables={"1": "Test"},
        )

    def test_returns_text_plus_nav_when_sid_unset(
        self, db_session, customer, clear_content_sids
    ):
        replies = handle_customer_message(db_session, customer, "hi")
        assert replies is not None
        assert len(replies) == 2
        assert_text_reply(replies[0], contains="Test")
        # Second reply is nav — also falls back to text since SID is cleared
        assert_text_reply(replies[1])

    def test_namaskaram_triggers_greeting(self, db_session, customer):
        replies = handle_customer_message(db_session, customer, "namaskaram")
        assert replies is not None
        assert len(replies) == 1
        assert replies[0].content_sid == settings.CONTENT_SID_GREETING

    def test_good_morning_triggers_greeting(self, db_session, customer):
        replies = handle_customer_message(db_session, customer, "good morning")
        assert replies is not None
        assert replies[0].content_sid == settings.CONTENT_SID_GREETING

    def test_loose_match_greeting_prefix(self, db_session, customer):
        # "hi anita how are you" → first word "hi" → greeting
        replies = handle_customer_message(db_session, customer, "hi anita how are you")
        assert replies is not None
        assert replies[0].content_sid == settings.CONTENT_SID_GREETING


# ============================================================
# Menu
# ============================================================


class TestMenu:
    """Menu returns [text_with_products, nav_template] when products are
    available, or [apology_only] when nothing is available today."""

    def test_returns_text_plus_nav_when_products_available(
        self, db_session, customer, stub_products
    ):
        replies = handle_customer_message(db_session, customer, "menu")
        assert replies is not None
        assert len(replies) == 2
        assert_text_reply(replies[0], contains="Test Puff")
        body = replies[0].body
        assert body is not None
        assert "Test Ladoo" in body
        # Second reply is the nav template
        assert_template_reply(replies[1], settings.CONTENT_SID_NAV)

    def test_menu_text_groups_by_category(self, db_session, customer, stub_products):
        replies = handle_customer_message(db_session, customer, "menu")
        assert replies is not None
        body = replies[0].body
        assert body is not None
        # Category headers are capitalized
        assert "*Savoury*" in body
        assert "*Sweet*" in body

    def test_menu_text_has_no_reply_footer(self, db_session, customer, stub_products):
        """Team-lead brief: 'Reply *new order*' footer should be GONE.

        With Content Templates carrying the nav buttons separately, the
        old text footer is no longer needed and was removed.
        """
        replies = handle_customer_message(db_session, customer, "menu")
        assert replies is not None
        body = replies[0].body
        assert body is not None
        assert "Reply" not in body
        assert "new order" not in body.lower()

    def test_menu_with_no_available_products_returns_apology_only(
        self, db_session, customer
    ):
        replies = handle_customer_message(db_session, customer, "menu")
        assert replies is not None
        assert len(replies) == 1
        assert_text_reply(replies[0], contains="no items are available")

    def test_menu_button_label_routes_to_menu(
        self, db_session, customer, stub_products
    ):
        """The bakeriq_fallback template's Menu button delivers 'Menu' as
        body. Should route to the menu handler."""
        replies = handle_customer_message(db_session, customer, "Menu")
        assert replies is not None
        body = replies[0].body
        assert body is not None
        assert "Test Puff" in body


# ============================================================
# Order Status
# ============================================================


class TestOrderStatus:
    def test_no_orders_returns_text_plus_nav(self, db_session, customer):
        replies = handle_customer_message(db_session, customer, "order status")
        assert replies is not None
        assert len(replies) == 2
        assert_text_reply(replies[0], contains="yet")
        assert_template_reply(replies[1], settings.CONTENT_SID_NAV)

    def test_with_real_order_shows_details_and_nav(
        self, db_session, customer_with_order
    ):
        cust, order = customer_with_order
        replies = handle_customer_message(db_session, cust, "order status")
        assert replies is not None
        assert len(replies) == 2
        body = replies[0].body
        assert body is not None
        # Order short ID is first 8 chars of the UUID
        assert str(order.id)[:8] in body
        # Status received → "Received" in label
        assert "Received" in body
        assert_template_reply(replies[1], settings.CONTENT_SID_NAV)


# ============================================================
# Reorder Last
# ============================================================


class TestReorderLast:
    def test_no_history_returns_text_plus_nav(self, db_session, customer):
        replies = handle_customer_message(db_session, customer, "reorder last")
        assert replies is not None
        assert len(replies) == 2
        assert_text_reply(replies[0], contains="previous orders")
        assert_template_reply(replies[1], settings.CONTENT_SID_NAV)

    def test_with_prior_order_returns_cart_link_template(
        self, db_session, customer_with_order
    ):
        cust, _ = customer_with_order
        replies = handle_customer_message(db_session, cust, "reorder last")
        assert replies is not None
        assert len(replies) == 1
        # Cart-link template with token in content_variables["1"]
        assert replies[0].content_sid == settings.CONTENT_SID_CART_LINK
        assert replies[0].content_variables is not None
        assert "1" in replies[0].content_variables
        token = replies[0].content_variables["1"]
        # Tokens are URL-safe random strings, not empty
        assert isinstance(token, str)
        assert len(token) > 8


# ============================================================
# New Order
# ============================================================


class TestNewOrder:
    def test_returns_cart_link_template_with_token(self, db_session, customer):
        replies = handle_customer_message(db_session, customer, "new order")
        assert replies is not None
        assert len(replies) == 1
        assert replies[0].content_sid == settings.CONTENT_SID_CART_LINK
        assert replies[0].content_variables is not None
        assert "1" in replies[0].content_variables
        assert len(replies[0].content_variables["1"]) > 8

    def test_fallback_to_text_when_sid_unset(
        self, db_session, customer, clear_content_sids
    ):
        replies = handle_customer_message(db_session, customer, "new order")
        assert replies is not None
        assert len(replies) == 1
        assert_text_reply(replies[0], contains="/new/")
        body = replies[0].body
        assert body is not None
        assert "30 minutes" in body


# ============================================================
# Button label dispatch (case-insensitivity)
# ============================================================


class TestButtonLabelDispatch:
    """Twilio delivers button taps as the verbatim button label (with the
    exact capitalization shown). The dispatcher lowercases before matching,
    so any casing should work."""

    def test_reorder_last_exact_case(self, db_session, customer_with_order):
        cust, _ = customer_with_order
        replies = handle_customer_message(db_session, cust, "Reorder last")
        assert replies is not None
        assert replies[0].content_sid == settings.CONTENT_SID_CART_LINK

    def test_new_order_exact_case(self, db_session, customer):
        replies = handle_customer_message(db_session, customer, "New order")
        assert replies is not None
        assert replies[0].content_sid == settings.CONTENT_SID_CART_LINK

    def test_order_status_exact_case(self, db_session, customer):
        replies = handle_customer_message(db_session, customer, "Order status")
        assert replies is not None
        assert_text_reply(replies[0], contains="yet")


# ============================================================
# LLM fallback (None return preserves the existing contract)
# ============================================================


class TestLLMFallback:
    """Free text that doesn't match any keyword or button label must
    return None so the webhook routes to the parse_and_send Celery task."""

    def test_free_text_returns_none(self, db_session, customer):
        replies = handle_customer_message(
            db_session, customer, "2 veg puff and 1 ladoo please"
        )
        assert replies is None

    def test_gibberish_returns_none(self, db_session, customer):
        replies = handle_customer_message(db_session, customer, "qwerty asdfgh")
        assert replies is None

    def test_empty_string_returns_none(self, db_session, customer):
        replies = handle_customer_message(db_session, customer, "")
        assert replies is None
