"""Tests for the customer handler — bot logic for registered customers."""

import pytest

from app.models.category import Category
from app.models.customer import Customer
from app.models.product import Product
from app.services.customer_handler import handle_customer_message


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
    yield c
    db_session.delete(c)
    db_session.commit()


@pytest.fixture
def stub_products(db_session):
    """Two cheap products in a fresh category for menu rendering tests."""
    cat = Category(name="test_category", display_order=99, is_active=True)
    db_session.add(cat)
    db_session.flush()

    p1 = Product(
        name="Test Item A",
        category_id=cat.id,
        unit_price=10,
        unit_label="piece",
        is_available_today=True,
        is_active=True,
    )
    p2 = Product(
        name="Test Item B",
        category_id=cat.id,
        unit_price=20,
        unit_label="piece",
        is_available_today=True,
        is_active=True,
    )
    db_session.add_all([p1, p2])
    db_session.commit()
    yield [p1, p2]
    db_session.delete(p1)
    db_session.delete(p2)
    db_session.delete(cat)
    db_session.commit()


def test_greeting_returns_time_of_day_with_first_name(db_session, customer):
    reply = handle_customer_message(db_session, customer, "hi")
    assert reply is not None
    assert "Test" in reply  # first name
    assert "Reorder last" in reply
    assert "New order" in reply
    assert "Order status" in reply


def test_namaskaram_triggers_greeting(db_session, customer):
    reply = handle_customer_message(db_session, customer, "namaskaram")
    assert reply is not None
    assert "Test" in reply


def test_menu_lists_available_products(db_session, customer, stub_products):
    reply = handle_customer_message(db_session, customer, "menu")
    assert reply is not None
    assert "Test Item A" in reply
    assert "Test Item B" in reply
    assert "10" in reply  # price
    assert "20" in reply


def test_order_status_with_no_orders(db_session, customer):
    reply = handle_customer_message(db_session, customer, "order status")
    assert reply is not None
    assert "yet" in reply.lower()


def test_button_tap_returns_none_for_web_app_routing(db_session, customer):
    """'Reorder last' and 'New order' button taps fall through to
    web-app issuance (Task 5). Until that's wired, they return None —
    the dispatcher routes those through the LLM placeholder.
    """
    assert handle_customer_message(db_session, customer, "Reorder last") is None
    assert handle_customer_message(db_session, customer, "New order") is None


def test_free_text_returns_none_for_llm_fallback(db_session, customer):
    reply = handle_customer_message(db_session, customer, "2 veg puff and 1 ladoo please")
    assert reply is None


def test_gibberish_returns_none_for_llm_fallback(db_session, customer):
    reply = handle_customer_message(db_session, customer, "qwerty asdfgh")
    assert reply is None
