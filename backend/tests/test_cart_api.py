"""Tests for the cart API — token-authenticated endpoints used by the
customer web app to load, save, and place orders.

The cart endpoints don't use the standard owner-dashboard auth headers
since the token in the URL IS the auth. So no auth_headers fixture
needed — just a fresh client and seeded data.

We test against the truncated DB in conftest. Each test seeds exactly
what it needs (customer, products, optionally a prior order) so the
intent of each test is visible at a glance.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from app.models.category import Category
from app.models.customer import Customer
from app.models.order import Order, OrderItem, OrderStatus
from app.models.product import Product
from app.services import cart_cache
from app.services.token_service import consume_token, issue_token


@pytest.fixture
def customer(db_session):
    """A persisted customer that tokens attach to."""
    c = Customer(
        name="Cart Tester",
        primary_phone="+919888777333",
        whatsapp_enabled=True,
        is_active=True,
    )
    db_session.add(c)
    db_session.commit()
    db_session.refresh(c)
    return c


@pytest.fixture
def products(db_session):
    """Two products in one category — enough for cart variety."""
    cat = Category(name="cart_test_cat", display_order=99, is_active=True)
    db_session.add(cat)
    db_session.flush()

    p1 = Product(
        name="Test Bun",
        category_id=cat.id,
        unit_price=Decimal("20.00"),
        unit_label="piece",
        is_available_today=True,
        is_active=True,
    )
    p2 = Product(
        name="Test Cake",
        category_id=cat.id,
        unit_price=Decimal("100.00"),
        unit_label="piece",
        is_available_today=True,
        is_active=True,
    )
    db_session.add_all([p1, p2])
    db_session.commit()
    db_session.refresh(p1)
    db_session.refresh(p2)
    return [p1, p2]


@pytest.fixture(autouse=True)
def _clear_redis_between_tests():
    """Cart cache lives in Redis — wipe relevant keys between tests so
    one test's saved cart doesn't leak into the next."""
    from app.core.redis_client import get_redis

    r = get_redis()
    for key in r.scan_iter("cart:*"):
        r.delete(key)
    yield
    for key in r.scan_iter("cart:*"):
        r.delete(key)


def _seed_prior_order(db_session, customer, products, *, status=OrderStatus.received):
    """Helper — create a completed (non-draft) order so 'reorder' has
    something to pre-fill from."""
    order = Order(
        customer_id=customer.id,
        status=status,
        is_draft=False,
        notes=None,
        total_amount=Decimal("0"),  # set below from items
    )
    db_session.add(order)
    db_session.flush()

    p1, p2 = products
    items = [
        OrderItem(
            order_id=order.id,
            product_id=p1.id,
            product_name=p1.name,
            unit_price=p1.unit_price,
            unit_label=p1.unit_label,
            quantity=3,
            subtotal=p1.unit_price * 3,
        ),
        OrderItem(
            order_id=order.id,
            product_id=p2.id,
            product_name=p2.name,
            unit_price=p2.unit_price,
            unit_label=p2.unit_label,
            quantity=1,
            subtotal=p2.unit_price * 1,
        ),
    ]
    db_session.add_all(items)
    order.total_amount = sum(i.subtotal for i in items)
    db_session.commit()
    db_session.refresh(order)
    return order


# === GET /api/v1/cart/<token> ===


def test_load_cart_invalid_token_returns_404(client):
    """Unknown tokens get a friendly 404."""
    resp = client.get("/api/v1/cart/does-not-exist")
    assert resp.status_code == 404
    assert "expired" in resp.json()["detail"].lower()


def test_load_cart_expired_token_returns_404(db_session, client, customer):
    """Expired tokens are also 404 (not leaking that the token ever existed)."""
    tok = issue_token(db_session, customer=customer, kind="reorder")
    tok.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db_session.commit()

    resp = client.get(f"/api/v1/cart/{tok.token}")
    assert resp.status_code == 404


def test_load_cart_consumed_token_returns_404(db_session, client, customer):
    """Tokens consumed by a prior place-order are 404."""
    tok = issue_token(db_session, customer=customer, kind="reorder")
    consume_token(db_session, tok)
    db_session.commit()

    resp = client.get(f"/api/v1/cart/{tok.token}")
    assert resp.status_code == 404


def test_load_cart_reorder_with_prior_order_prefills_items(
    db_session, client, customer, products
):
    """'reorder' kind pre-fills the cart from the customer's last order."""
    _seed_prior_order(db_session, customer, products)
    tok = issue_token(db_session, customer=customer, kind="reorder")
    db_session.commit()

    resp = client.get(f"/api/v1/cart/{tok.token}")
    assert resp.status_code == 200
    data = resp.json()

    assert data["kind"] == "reorder"
    assert data["customer"]["name"] == "Cart Tester"
    assert len(data["items"]) == 2

    # Items ordered by created_at — the bun (qty 3) came first
    bun = next(i for i in data["items"] if i["product_name"] == "Test Bun")
    cake = next(i for i in data["items"] if i["product_name"] == "Test Cake")
    assert bun["quantity"] == 3
    assert bun["subtotal"] == 60.0
    assert cake["quantity"] == 1
    assert cake["subtotal"] == 100.0
    assert data["total"] == 160.0


def test_load_cart_reorder_without_prior_order_returns_empty_items(
    db_session, client, customer, products
):
    """A 'reorder' link issued for a customer with no orders renders an
    empty cart — the menu is still included so they can pick fresh."""
    tok = issue_token(db_session, customer=customer, kind="reorder")
    db_session.commit()

    resp = client.get(f"/api/v1/cart/{tok.token}")
    assert resp.status_code == 200
    data = resp.json()

    assert data["items"] == []
    assert data["total"] == 0
    # Menu still populated
    assert len(data["menu"]) == 2


def test_load_cart_new_kind_returns_empty_items_and_menu(
    db_session, client, customer, products
):
    """'new' kind is always an empty cart with the menu — even if the
    customer has prior orders, we don't pre-fill (that's what reorder is for)."""
    _seed_prior_order(db_session, customer, products)
    tok = issue_token(db_session, customer=customer, kind="new")
    db_session.commit()

    resp = client.get(f"/api/v1/cart/{tok.token}")
    assert resp.status_code == 200
    data = resp.json()

    assert data["kind"] == "new"
    assert data["items"] == []
    assert len(data["menu"]) == 2


def test_load_cart_edit_without_cached_cart_returns_404(db_session, client, customer):
    """'edit' implies there's a cart in progress; if none exists in Redis,
    the link is stale and we 404."""
    tok = issue_token(db_session, customer=customer, kind="edit")
    db_session.commit()

    resp = client.get(f"/api/v1/cart/{tok.token}")
    assert resp.status_code == 404


def test_load_cart_skips_products_no_longer_available(
    db_session, client, customer, products
):
    """If a product from a prior order is now unavailable, it's silently
    dropped from the reorder pre-fill."""
    _seed_prior_order(db_session, customer, products)
    # Make the cake unavailable
    products[1].is_available_today = False
    db_session.commit()

    tok = issue_token(db_session, customer=customer, kind="reorder")
    db_session.commit()

    resp = client.get(f"/api/v1/cart/{tok.token}")
    assert resp.status_code == 200
    data = resp.json()

    # Only the bun remains
    assert len(data["items"]) == 1
    assert data["items"][0]["product_name"] == "Test Bun"


# === POST /api/v1/cart/<token> (save) ===


def test_save_cart_stores_items_and_returns_pricing(
    db_session, client, customer, products
):
    """Save endpoint accepts items, returns the recomputed cart payload
    with server-side prices and subtotals."""
    tok = issue_token(db_session, customer=customer, kind="new")
    db_session.commit()

    payload = {"items": [{"product_id": str(products[0].id), "quantity": 5}]}
    resp = client.post(f"/api/v1/cart/{tok.token}", json=payload)
    assert resp.status_code == 200
    data = resp.json()

    assert data["ok"] is True
    assert len(data["items"]) == 1
    assert data["items"][0]["quantity"] == 5
    assert data["items"][0]["subtotal"] == 100.0  # 5 × ₹20
    assert data["total"] == 100.0


def test_save_cart_drops_invalid_product_ids(db_session, client, customer, products):
    """Items referencing unavailable products are silently dropped on save."""
    products[1].is_active = False  # cake now inactive
    db_session.commit()

    tok = issue_token(db_session, customer=customer, kind="new")
    db_session.commit()

    payload = {
        "items": [
            {"product_id": str(products[0].id), "quantity": 2},
            {"product_id": str(products[1].id), "quantity": 1},  # cake — dropped
        ]
    }
    resp = client.post(f"/api/v1/cart/{tok.token}", json=payload)
    assert resp.status_code == 200
    data = resp.json()

    assert len(data["items"]) == 1
    assert data["items"][0]["product_name"] == "Test Bun"


def test_save_cart_rejects_expired_token(db_session, client, customer):
    """A POST to an expired token returns 404."""
    tok = issue_token(db_session, customer=customer, kind="new")
    tok.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db_session.commit()

    resp = client.post(f"/api/v1/cart/{tok.token}", json={"items": []})
    assert resp.status_code == 404


# === POST /api/v1/cart/<token>/place ===


def test_place_order_creates_order_and_consumes_token(
    db_session, client, customer, products
):
    """The full happy path: cart items → real Order row, token consumed."""
    tok = issue_token(db_session, customer=customer, kind="new")
    db_session.commit()
    token_str = tok.token

    payload = {
        "items": [
            {"product_id": str(products[0].id), "quantity": 2},
            {"product_id": str(products[1].id), "quantity": 1},
        ]
    }
    resp = client.post(f"/api/v1/cart/{token_str}/place", json=payload)
    assert resp.status_code == 200
    data = resp.json()

    assert data["ok"] is True
    assert data["total"] == 140.0  # 2×20 + 1×100
    assert "order_id" in data

    # Real order row exists, non-draft
    from uuid import UUID

    order = db_session.get(Order, UUID(data["order_id"]))
    assert order is not None
    assert order.is_draft is False
    assert order.customer_id == customer.id
    assert float(order.total_amount) == 140.0

    # Token is consumed — subsequent GETs return 404
    follow = client.get(f"/api/v1/cart/{token_str}")
    assert follow.status_code == 404


def test_place_order_rejects_empty_cart(db_session, client, customer):
    """Placing an order with no items returns 422 — refusing the no-op."""
    tok = issue_token(db_session, customer=customer, kind="new")
    db_session.commit()

    resp = client.post(f"/api/v1/cart/{tok.token}/place", json={"items": []})
    assert resp.status_code == 422
    assert "empty" in resp.json()["detail"].lower()


def test_place_order_clears_redis_cart(db_session, client, customer, products):
    """After place, the Redis cart cache for that token is cleared."""
    tok = issue_token(db_session, customer=customer, kind="new")
    db_session.commit()
    token_str = tok.token

    # Pre-seed the cache so we can confirm it's wiped
    cart_cache.save_cart(
        token_str,
        {"customer_id": str(customer.id), "kind": "new", "items": []},
    )
    assert cart_cache.get_cart(token_str) is not None

    payload = {"items": [{"product_id": str(products[0].id), "quantity": 1}]}
    resp = client.post(f"/api/v1/cart/{token_str}/place", json=payload)
    assert resp.status_code == 200

    # Cache cleared
    assert cart_cache.get_cart(token_str) is None


def test_place_order_rejects_expired_token(db_session, client, customer, products):
    """A POST .../place to an expired token returns 404 (and no order created)."""
    tok = issue_token(db_session, customer=customer, kind="new")
    tok.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db_session.commit()

    payload = {"items": [{"product_id": str(products[0].id), "quantity": 1}]}
    resp = client.post(f"/api/v1/cart/{tok.token}/place", json=payload)
    assert resp.status_code == 404
