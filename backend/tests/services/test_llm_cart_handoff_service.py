"""Tests for the LLM cart handoff service — Medium rigor.

These tests run against real Postgres + real Redis (per the existing
test_cart_api.py pattern). The handoff is end-to-end glue: token
issuance, Redis cart write, message text composition. Mocking any of
those would defeat the test's purpose.

Coverage:
  Cart write (3): items written to Redis with correct shape, token
                  matches the cart key, no items still writes a cart
  Message text (3): items + total formatted, dropped names shown,
                    dropped section omitted when empty
  Counts (1): HandoffResult counts match input

Total: 7 tests.
"""

from decimal import Decimal

import pytest
from app.models.category import Category
from app.models.customer import Customer
from app.models.product import Product
from app.services import cart_cache
from app.services.llm_cart_handoff_service import handoff_to_web
from app.services.product_matcher_service import MatchedItem


@pytest.fixture
def customer(db_session):
    c = Customer(
        name="Handoff Tester",
        primary_phone="+919888777444",
        whatsapp_enabled=True,
        is_active=True,
    )
    db_session.add(c)
    db_session.commit()
    db_session.refresh(c)
    return c


@pytest.fixture
def stub_products(db_session):
    """Two products with known prices for total-arithmetic checks."""
    cat = Category(name="handoff_test_cat", display_order=99, is_active=True)
    db_session.add(cat)
    db_session.flush()

    veg_puff = Product(
        name="Veg Puff",
        category_id=cat.id,
        unit_price=Decimal("18.00"),
        unit_label="piece",
        is_available_today=True,
        is_active=True,
    )
    ladoo = Product(
        name="Ladoo",
        category_id=cat.id,
        unit_price=Decimal("20.00"),
        unit_label="piece",
        is_available_today=True,
        is_active=True,
    )
    db_session.add_all([veg_puff, ladoo])
    db_session.commit()
    db_session.refresh(veg_puff)
    db_session.refresh(ladoo)
    return {"veg_puff": veg_puff, "ladoo": ladoo}


@pytest.fixture(autouse=True)
def _clear_redis_between_tests():
    """Wipe cart cache between tests — same pattern as test_cart_api.py."""
    from app.core.redis_client import get_redis

    r = get_redis()
    for key in r.scan_iter("cart:*"):
        r.delete(key)
    yield
    for key in r.scan_iter("cart:*"):
        r.delete(key)


def _matched_from(product: Product, quantity: int, via: str = "name") -> MatchedItem:
    """Build a MatchedItem from a Product row — saves a few lines per test."""
    return MatchedItem(
        product_id=product.id,
        product_name=product.name,
        quantity=quantity,
        matched_via=via,
    )


# === CART WRITE ===


def test_handoff_writes_cart_to_redis(db_session, customer, stub_products):
    """The matched items land in Redis under cart:<token> with the shape
    api/v1/cart.py reads."""
    matched = [
        _matched_from(stub_products["veg_puff"], 2),
        _matched_from(stub_products["ladoo"], 1),
    ]
    result = handoff_to_web(
        db_session, customer=customer, matched=matched, dropped_names=[]
    )
    db_session.commit()

    cart = cart_cache.get_cart(result.token)
    assert cart is not None
    assert cart["customer_id"] == str(customer.id)
    assert cart["kind"] == "new"
    assert len(cart["items"]) == 2

    # Items match the matcher's product_id + quantity
    items_by_pid = {item["product_id"]: item["quantity"] for item in cart["items"]}
    assert items_by_pid[str(stub_products["veg_puff"].id)] == 2
    assert items_by_pid[str(stub_products["ladoo"].id)] == 1


def test_handoff_token_matches_cart_key(db_session, customer, stub_products):
    """The returned token must be the exact key used in Redis — if these
    diverge, the customer's web app cart appears empty (the silent bug
    we caught in Substep 5)."""
    matched = [_matched_from(stub_products["veg_puff"], 1)]
    result = handoff_to_web(
        db_session, customer=customer, matched=matched, dropped_names=[]
    )
    db_session.commit()

    # Token is the 32-char raw token, not the full URL
    assert len(result.token) == 32
    assert "/" not in result.token  # no URL fragments leaking through
    # And the cart lives at exactly that key
    assert cart_cache.get_cart(result.token) is not None


def test_handoff_empty_matched_still_writes_cart(db_session, customer):
    """Even with zero matched items, we still write a cart (empty items
    list). The caller decides whether to surface the link or use a
    fallback message — that's the dispatcher's job."""
    result = handoff_to_web(db_session, customer=customer, matched=[], dropped_names=[])
    db_session.commit()

    cart = cart_cache.get_cart(result.token)
    assert cart is not None
    assert cart["items"] == []


# === MESSAGE TEXT ===


def test_message_text_includes_items_and_total(db_session, customer, stub_products):
    """The customer sees what we understood + the total before they tap."""
    matched = [
        _matched_from(stub_products["veg_puff"], 2),  # 2 × 18 = 36
        _matched_from(stub_products["ladoo"], 1),  # 1 × 20 = 20
    ]
    result = handoff_to_web(
        db_session, customer=customer, matched=matched, dropped_names=[]
    )
    db_session.commit()

    msg = result.message_text
    assert "Veg Puff × 2" in msg
    assert "Ladoo × 1" in msg
    assert "₹36.00" in msg
    assert "₹20.00" in msg
    assert "Total: ₹56.00" in msg
    assert result.link in msg


def test_message_text_includes_dropped_names(db_session, customer, stub_products):
    """Dropped items appear in the message so the customer isn't
    surprised something is missing."""
    matched = [_matched_from(stub_products["veg_puff"], 1)]
    result = handoff_to_web(
        db_session,
        customer=customer,
        matched=matched,
        dropped_names=["samosa", "brownie"],
    )
    db_session.commit()

    msg = result.message_text
    # Dropped names appear, sorted for stability
    assert "brownie" in msg
    assert "samosa" in msg
    assert "couldn't find" in msg.lower()


def test_message_text_omits_dropped_section_when_empty(
    db_session, customer, stub_products
):
    """No dropped items → no 'couldn't find' line at all."""
    matched = [_matched_from(stub_products["veg_puff"], 1)]
    result = handoff_to_web(
        db_session, customer=customer, matched=matched, dropped_names=[]
    )
    db_session.commit()

    msg = result.message_text
    assert "couldn't find" not in msg.lower()


# === COUNTS ===


def test_handoff_result_counts_match_input(db_session, customer, stub_products):
    """HandoffResult.matched_count and dropped_names round-trip correctly."""
    matched = [
        _matched_from(stub_products["veg_puff"], 1),
        _matched_from(stub_products["ladoo"], 2),
    ]
    dropped = ["samosa"]
    result = handoff_to_web(
        db_session, customer=customer, matched=matched, dropped_names=dropped
    )
    db_session.commit()

    assert result.matched_count == 2
    assert result.dropped_names == ["samosa"]
