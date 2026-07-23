"""Tests for inventory — stock levels, order hooks, and the prep list.

Weighted toward the order hooks. A missed deduction is visible and
annoying; a missed *restore* is silent and permanent — the count drifts
down every time an order is cancelled and there's nothing to reconcile
against. So cancel, edit, and draft paths get more attention than the
happy path.

Two product kinds throughout:

  stockable      sealed goods with a countable quantity (ladoo packets)
  made-to-order  baked and sold same day, no stock (puffs)

An order routinely mixes both, which is where most of the edge cases live.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from app.models.category import Category
from app.models.customer import Customer
from app.models.order import Order, OrderStatus
from app.models.product import Product
from app.schemas.order import OrderCreate, OrderItemWrite, OrderUpdate
from app.services import inventory_service, order_service
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

TODAY = date(2026, 7, 23)


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def category(db_session: Session) -> Category:
    c = Category(name="inventory_test_cat", display_order=99, is_active=True)
    db_session.add(c)
    db_session.commit()
    db_session.refresh(c)
    return c


@pytest.fixture
def stocked(db_session: Session, category: Category) -> Product:
    """A sealed product with 20 on hand, warning at 5."""
    p = Product(
        name="Ladoo Packet",
        category_id=category.id,
        unit_price=Decimal("15.00"),
        unit_label="packet",
        is_available_today=True,
        is_active=True,
        is_stockable=True,
        stock_quantity=20,
        low_stock_threshold=5,
    )
    db_session.add(p)
    db_session.commit()
    db_session.refresh(p)
    return p


@pytest.fixture
def made_to_order(db_session: Session, category: Category) -> Product:
    """A puff — baked to order, no stock."""
    p = Product(
        name="Veg Puff",
        category_id=category.id,
        unit_price=Decimal("18.00"),
        unit_label="piece",
        is_available_today=True,
        is_active=True,
        is_stockable=False,
    )
    db_session.add(p)
    db_session.commit()
    db_session.refresh(p)
    return p


@pytest.fixture
def customer(db_session: Session) -> Customer:
    c = Customer(
        name="Stock Tester",
        primary_phone="+919888555001",
        whatsapp_enabled=True,
        is_active=True,
        address_line_1="1 Stock Road",
        city="Kochi",
        state="Kerala",
        pincode="682020",
    )
    db_session.add(c)
    db_session.commit()
    db_session.refresh(c)
    return c


def _place(
    db_session: Session,
    customer: Customer,
    lines: list[tuple[Product, int]],
    *,
    order_date: date = TODAY,
) -> Order:
    """Place a real order through the service, so the hooks fire."""
    return order_service.create_order(
        db_session,
        OrderCreate(
            customer_id=customer.id,
            order_date=order_date,
            items=[OrderItemWrite(product_id=p.id, quantity=q) for p, q in lines],
        ),
    )


# ============================================================
# Order hooks — the part that can corrupt data
# ============================================================


class TestStockOnOrder:
    def test_placing_deducts(self, db_session, customer, stocked):
        _place(db_session, customer, [(stocked, 3)])
        db_session.refresh(stocked)
        assert stocked.stock_quantity == 17

    def test_cancelling_restores(self, db_session, customer, stocked):
        order = _place(db_session, customer, [(stocked, 3)])
        db_session.refresh(stocked)
        assert stocked.stock_quantity == 17

        order_service.change_status(db_session, order.id, OrderStatus.cancelled)
        db_session.refresh(stocked)
        assert stocked.stock_quantity == 20

    def test_cancelling_twice_restores_once(self, db_session, customer, stocked):
        """Otherwise a double-tap invents stock out of nothing."""
        order = _place(db_session, customer, [(stocked, 3)])
        order_service.change_status(db_session, order.id, OrderStatus.cancelled)
        order_service.change_status(db_session, order.id, OrderStatus.cancelled)

        db_session.refresh(stocked)
        assert stocked.stock_quantity == 20

    def test_forward_status_moves_leave_stock_alone(
        self, db_session, customer, stocked
    ):
        """Stock is reserved at placement. Preparing and delivering are
        progress, not further consumption."""
        order = _place(db_session, customer, [(stocked, 3)])
        order_service.change_status(db_session, order.id, OrderStatus.preparing)
        order_service.change_status(db_session, order.id, OrderStatus.ready)
        order_service.change_status(db_session, order.id, OrderStatus.delivering)

        db_session.refresh(stocked)
        assert stocked.stock_quantity == 17

    def test_made_to_order_untouched(self, db_session, customer, made_to_order):
        """Puffs have no stock to move."""
        _place(db_session, customer, [(made_to_order, 5)])
        db_session.refresh(made_to_order)
        assert made_to_order.stock_quantity is None

    def test_mixed_order_only_touches_stockable(
        self, db_session, customer, stocked, made_to_order
    ):
        """The common real case — a packet of ladoo and some puffs."""
        _place(db_session, customer, [(stocked, 2), (made_to_order, 4)])

        db_session.refresh(stocked)
        db_session.refresh(made_to_order)
        assert stocked.stock_quantity == 18
        assert made_to_order.stock_quantity is None

    def test_stock_may_go_negative(self, db_session, customer, stocked):
        """The count drifts — someone sells over the counter without
        touching the dashboard. Refusing the order on a stale number is
        worse than showing the owner a negative to correct."""
        _place(db_session, customer, [(stocked, 25)])
        db_session.refresh(stocked)
        assert stocked.stock_quantity == -5

    def test_untracked_stockable_stays_none(self, db_session, customer, category):
        """Stockable but never counted. Deducting from an assumed zero
        would invent a number the owner never entered."""
        p = Product(
            name="Uncounted Biscuits",
            category_id=category.id,
            unit_price=Decimal("30.00"),
            unit_label="packet",
            is_available_today=True,
            is_active=True,
            is_stockable=True,
            stock_quantity=None,
        )
        db_session.add(p)
        db_session.commit()

        _place(db_session, customer, [(p, 3)])
        db_session.refresh(p)
        assert p.stock_quantity is None


class TestStockOnEdit:
    def test_reducing_quantity_gives_stock_back(self, db_session, customer, stocked):
        """Items are replaced wholesale, so an edit has to restore the old
        lines before deducting the new — not compute a delta."""
        order = _place(db_session, customer, [(stocked, 5)])
        db_session.refresh(stocked)
        assert stocked.stock_quantity == 15

        order_service.update_order(
            db_session,
            order.id,
            OrderUpdate(items=[OrderItemWrite(product_id=stocked.id, quantity=2)]),
        )
        db_session.refresh(stocked)
        assert stocked.stock_quantity == 18

    def test_increasing_quantity_deducts_the_difference(
        self, db_session, customer, stocked
    ):
        order = _place(db_session, customer, [(stocked, 2)])
        order_service.update_order(
            db_session,
            order.id,
            OrderUpdate(items=[OrderItemWrite(product_id=stocked.id, quantity=6)]),
        )
        db_session.refresh(stocked)
        assert stocked.stock_quantity == 14

    def test_removing_an_item_restores_it_fully(
        self, db_session, customer, stocked, made_to_order
    ):
        order = _place(db_session, customer, [(stocked, 4), (made_to_order, 2)])
        db_session.refresh(stocked)
        assert stocked.stock_quantity == 16

        order_service.update_order(
            db_session,
            order.id,
            OrderUpdate(
                items=[OrderItemWrite(product_id=made_to_order.id, quantity=2)]
            ),
        )
        db_session.refresh(stocked)
        assert stocked.stock_quantity == 20

    def test_editing_notes_only_leaves_stock_alone(self, db_session, customer, stocked):
        order = _place(db_session, customer, [(stocked, 3)])
        order_service.update_order(
            db_session, order.id, OrderUpdate(notes="ring twice")
        )
        db_session.refresh(stocked)
        assert stocked.stock_quantity == 17


# ============================================================
# Low stock
# ============================================================


class TestLowStock:
    def test_flags_at_threshold(self, db_session, stocked):
        stocked.stock_quantity = 5
        db_session.commit()
        assert inventory_service.is_low_stock(stocked) is True

    def test_flags_below_threshold(self, db_session, stocked):
        stocked.stock_quantity = 2
        db_session.commit()
        assert inventory_service.is_low_stock(stocked) is True

    def test_not_flagged_above(self, db_session, stocked):
        assert inventory_service.is_low_stock(stocked) is False

    def test_no_threshold_means_no_warning(self, db_session, stocked):
        """An absent threshold means the owner doesn't want nagging about
        this one, even at zero."""
        stocked.stock_quantity = 0
        stocked.low_stock_threshold = None
        db_session.commit()
        assert inventory_service.is_low_stock(stocked) is False

    def test_made_to_order_never_low(self, db_session, made_to_order):
        assert inventory_service.is_low_stock(made_to_order) is False

    def test_ordering_can_trigger_low(self, db_session, customer, stocked):
        assert inventory_service.is_low_stock(stocked) is False
        _place(db_session, customer, [(stocked, 16)])
        db_session.refresh(stocked)
        assert stocked.stock_quantity == 4
        assert inventory_service.is_low_stock(stocked) is True


# ============================================================
# Prep list
# ============================================================


class TestPrepList:
    def test_aggregates_made_to_order_only(
        self, db_session, customer, stocked, made_to_order
    ):
        _place(db_session, customer, [(stocked, 2), (made_to_order, 3)])
        _place(db_session, customer, [(made_to_order, 4)])

        rows = inventory_service.get_prep_list(db_session, for_date=TODAY)
        names = {r["product_name"] for r in rows}
        assert "Veg Puff" in names
        assert "Ladoo Packet" not in names

        puff = next(r for r in rows if r["product_name"] == "Veg Puff")
        assert puff["quantity"] == 7
        assert puff["order_count"] == 2

    def test_excludes_cancelled(self, db_session, customer, made_to_order):
        _place(db_session, customer, [(made_to_order, 3)])
        cancelled = _place(db_session, customer, [(made_to_order, 10)])
        order_service.change_status(db_session, cancelled.id, OrderStatus.cancelled)

        rows = inventory_service.get_prep_list(db_session, for_date=TODAY)
        puff = next(r for r in rows if r["product_name"] == "Veg Puff")
        assert puff["quantity"] == 3

    def test_scoped_to_the_date(self, db_session, customer, made_to_order):
        _place(db_session, customer, [(made_to_order, 3)], order_date=TODAY)
        _place(
            db_session,
            customer,
            [(made_to_order, 99)],
            order_date=date(2026, 7, 24),
        )

        rows = inventory_service.get_prep_list(db_session, for_date=TODAY)
        puff = next(r for r in rows if r["product_name"] == "Veg Puff")
        assert puff["quantity"] == 3

    def test_empty_when_nothing_ordered(self, db_session):
        assert inventory_service.get_prep_list(db_session, for_date=TODAY) == []

    @pytest.mark.parametrize(
        "hour,visible",
        [
            (3, False),  # before the 5 AM order cutoff — demand still moving
            (5, True),  # cutoff, orders locked
            (13, True),
            (20, True),
            (21, False),  # baking done
            (23, False),
        ],
    )
    def test_visibility_window(self, hour, visible):
        now = datetime(2026, 7, 23, hour, 0)
        assert inventory_service.prep_list_is_visible(now) is visible


# ============================================================
# Endpoints
# ============================================================


class TestInventoryEndpoints:
    def test_stock_list(self, client: TestClient, db_session, stocked, auth_headers):
        r = client.get("/api/v1/inventory/stock", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert data["total"] == 1
        assert data["items"][0]["name"] == "Ladoo Packet"
        assert data["items"][0]["stock_quantity"] == 20

    def test_stock_list_omits_made_to_order(
        self, client: TestClient, db_session, stocked, made_to_order, auth_headers
    ):
        r = client.get("/api/v1/inventory/stock", headers=auth_headers)
        names = {i["name"] for i in r.json()["items"]}
        assert "Veg Puff" not in names

    def test_low_only_filter(
        self, client: TestClient, db_session, stocked, category, auth_headers
    ):
        low = Product(
            name="Nearly Out",
            category_id=category.id,
            unit_price=Decimal("10.00"),
            unit_label="packet",
            is_active=True,
            is_stockable=True,
            stock_quantity=1,
            low_stock_threshold=5,
        )
        db_session.add(low)
        db_session.commit()

        r = client.get(
            "/api/v1/inventory/stock", params={"low_only": True}, headers=auth_headers
        )
        data = r.json()
        assert data["total"] == 1
        assert data["items"][0]["name"] == "Nearly Out"
        assert data["low_stock_count"] == 1

    def test_set_stock(self, client: TestClient, db_session, stocked, auth_headers):
        r = client.patch(
            f"/api/v1/inventory/stock/{stocked.id}",
            headers=auth_headers,
            json={"quantity": 42},
        )
        assert r.status_code == 200
        assert r.json()["stock_quantity"] == 42

        db_session.refresh(stocked)
        assert stocked.stock_quantity == 42

    def test_set_stock_rejects_made_to_order(
        self, client: TestClient, made_to_order, auth_headers
    ):
        """A count on a puff would be a number nothing maintains."""
        r = client.patch(
            f"/api/v1/inventory/stock/{made_to_order.id}",
            headers=auth_headers,
            json={"quantity": 10},
        )
        assert r.status_code == 422

    def test_set_stock_404(self, client: TestClient, auth_headers):
        r = client.patch(
            f"/api/v1/inventory/stock/{uuid4()}",
            headers=auth_headers,
            json={"quantity": 10},
        )
        assert r.status_code == 404

    def test_enabling_tracking_starts_at_zero(
        self, client: TestClient, db_session, made_to_order, auth_headers
    ):
        r = client.patch(
            f"/api/v1/inventory/settings/{made_to_order.id}",
            headers=auth_headers,
            json={"is_stockable": True, "low_stock_threshold": 3},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["stock_quantity"] == 0
        assert data["low_stock_threshold"] == 3

    def test_disabling_tracking_clears_the_count(
        self, client: TestClient, db_session, stocked, auth_headers
    ):
        """A number nothing maintains goes stale, and a stale number is
        worse than none."""
        r = client.patch(
            f"/api/v1/inventory/settings/{stocked.id}",
            headers=auth_headers,
            json={"is_stockable": False},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["stock_quantity"] is None
        assert data["low_stock_threshold"] is None

    def test_prep_endpoint(
        self, client: TestClient, db_session, customer, made_to_order, auth_headers
    ):
        _place(db_session, customer, [(made_to_order, 6)], order_date=date.today())

        r = client.get("/api/v1/inventory/prep", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert data["total"] == 1
        assert data["items"][0]["quantity"] == 6
        assert isinstance(data["is_visible"], bool)

    def test_stock_requires_auth(self, client: TestClient):
        assert client.get("/api/v1/inventory/stock").status_code == 401

    def test_prep_requires_auth(self, client: TestClient):
        assert client.get("/api/v1/inventory/prep").status_code == 401

    def test_set_stock_requires_auth(self, client: TestClient, stocked):
        r = client.patch(f"/api/v1/inventory/stock/{stocked.id}", json={"quantity": 5})
        assert r.status_code == 401
